"""
APScheduler — WhatsApp message scheduler.
Runs inside FastAPI process (no Redis/Celery needed).

Schedule:
  1. Confirmation   — triggered immediately on new booking (if phone exists)
  2. Pre-arrival    — 48h before check_in at 10:00  ← מדולג אם פחות מ-48h
  3. Entry code     — day of check_in: 2h before checkin_time
  4. Checkout       — 2h before checkout_time
  5. Review         — manual only (from dashboard)
"""
import logging
from datetime import date, datetime, time, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.integrations.whatsapp import send_whatsapp
from app.models import Booking, MessageLog

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")


# ---------------------------------------------------------------------------
# Public helpers — called from webhook / other routes
# ---------------------------------------------------------------------------

async def trigger_confirmation(booking: Booking, db: AsyncSession):
    """Send confirmation immediately (message type 1)."""
    if not booking.guest_phone:
        logger.info(f"Booking {booking.id}: no phone, skipping confirmation")
        return
    await _send_if_not_sent(booking.id, "confirmation", booking.guest_phone,
                             _build_body("confirmation", booking), db)


def schedule_booking_messages(booking: Booking):
    """
    Register all timed messages for a booking into APScheduler.
    Call this after a booking is created/updated with a phone number.

    Logic:
    - Pre-arrival (48h before): נשלח רק אם יש יותר מ-48 שעות לכניסה
    - Entry code: תמיד מתוזמן (אם בעתיד)
    - Checkout: תמיד מתוזמן (אם בעתיד)
    """
    if not booking.guest_phone or not booking.check_in:
        return

    phone = booking.guest_phone
    bid = booking.id
    now = datetime.now()

    # 2. Pre-arrival — 48h before check_in at 10:00
    #    מדלגים אם ההזמנה נכנסה פחות מ-48 שעות לפני הכניסה
    pre_arrival_dt = datetime.combine(booking.check_in - timedelta(days=2), time(10, 0))
    hours_to_checkin = (datetime.combine(booking.check_in, time(14, 0)) - now).total_seconds() / 3600

    if hours_to_checkin > 48:
        _add_job(f"pre_arrival_{bid}", pre_arrival_dt, bid, "pre_arrival", phone, booking)
    else:
        logger.info(f"Booking {bid}: skipping pre_arrival — only {hours_to_checkin:.1f}h to check-in")

    # 3. Entry code — check_in day, 2h before checkin_time
    checkin_time = _parse_time(booking.checkin_time) if booking.checkin_time else _checkin_time(booking.check_in)
    entry_dt = datetime.combine(booking.check_in, checkin_time) - timedelta(hours=2)
    _add_job(f"entry_{bid}", entry_dt, bid, "entry_code", phone, booking)

    # 4. Checkout — 2h before checkout_time
    checkout_time = _parse_time(booking.checkout_time) if booking.checkout_time else _checkout_time(booking.check_in)
    checkout_dt = datetime.combine(booking.check_out, checkout_time) - timedelta(hours=2)
    _add_job(f"checkout_{bid}", checkout_dt, bid, "checkout", phone, booking)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_job(job_id: str, run_at: datetime, booking_id: int,
             message_type: str, phone: str, booking: Booking):
    now = datetime.now()
    if run_at <= now:
        logger.info(f"Skipping past job {job_id} scheduled for {run_at}")
        return

    scheduler.add_job(
        _send_scheduled,
        trigger=DateTrigger(run_date=run_at),
        id=job_id,
        replace_existing=True,
        kwargs={
            "booking_id": booking_id,
            "message_type": message_type,
            "phone": phone,
            "body": _build_body(message_type, booking),
        },
    )
    logger.info(f"Scheduled {job_id} for {run_at}")


async def _send_scheduled(booking_id: int, message_type: str, phone: str, body: str):
    """Job function — opens its own DB session."""
    async with AsyncSessionLocal() as db:
        # לפני שליחת קוד כניסה — צור קוד ב-TTLock ועדכן את body
        if message_type == "entry_code":
            body = await _create_ttlock_and_build_body(booking_id, db) or body
        # לאחר שליחת הודעת יציאה — מחק קוד TTLock
        if message_type == "checkout":
            await _delete_ttlock_after_checkout(booking_id, db)
        await _send_if_not_sent(booking_id, message_type, phone, body, db)


async def _create_ttlock_and_build_body(booking_id: int, db: AsyncSession) -> str | None:
    """
    יוצר קוד כניסה ב-TTLock, שומר ב-booking.entry_code,
    ומחזיר את גוף הודעת ה-WhatsApp עם הקוד האמיתי.
    """
    from sqlalchemy import select as sa_select
    from app.integrations.ttlock import assign_passcode_to_booking

    try:
        result = await db.execute(sa_select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if not booking:
            logger.error(f"TTLock: booking {booking_id} not found")
            return None

        code = await assign_passcode_to_booking(booking, db)
        if not code:
            logger.error(f"TTLock: failed to create code for booking {booking_id}")
            return None

        logger.info(f"TTLock: code {code} created for booking {booking_id}")
        return _build_body("entry_code", booking)

    except Exception as e:
        logger.error(f"TTLock error for booking {booking_id}: {e}")
        return None



async def _delete_ttlock_after_checkout(booking_id: int, db: AsyncSession):
    """מוחק קוד TTLock אחרי יציאה."""
    from sqlalchemy import select as sa_select
    from app.integrations.ttlock import remove_passcode_after_checkout

    try:
        result = await db.execute(sa_select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if booking:
            await remove_passcode_after_checkout(booking, db)
            logger.info(f"TTLock: code deleted for booking {booking_id} after checkout")
    except Exception as e:
        logger.error(f"TTLock delete error for booking {booking_id}: {e}")


async def _send_if_not_sent(booking_id: int, message_type: str,
                             phone: str, body: str, db: AsyncSession):
    """Send only if not already logged (idempotency)."""
    existing = await db.execute(
        select(MessageLog).where(
            MessageLog.booking_id == booking_id,
            MessageLog.message_type == message_type,
        )
    )
    if existing.scalar_one_or_none():
        logger.info(f"Booking {booking_id}: {message_type} already sent, skipping")
        return

    try:
        sid = send_whatsapp(phone, body)
        status = "sent"
    except Exception as e:
        logger.error(f"WhatsApp send failed for booking {booking_id}: {e}")
        sid = None
        status = "failed"

    log = MessageLog(
        booking_id=booking_id,
        phone=phone,
        message_type=message_type,
        body=body,
        status=status,
        twilio_sid=sid,
    )
    db.add(log)
    await db.commit()
    logger.info(f"Booking {booking_id}: {message_type} → {status}")


def _parse_time(time_str: str) -> time:
    """Parse 'HH:MM' string to time object, fallback to 14:00."""
    try:
        h, m = time_str.strip().split(":")
        return time(int(h), int(m))
    except Exception:
        return time(14, 0)


def _checkin_time(d: date) -> time:
    """16:00 on Saturday, 14:00 otherwise."""
    return time(16, 0) if d.isoweekday() == 6 else time(14, 0)


def _checkout_time(checkin: date) -> time:
    """14:00 if checkout is Saturday, 12:00 otherwise."""
    checkout_weekday = (checkin + timedelta(days=1)).isoweekday()
    return time(14, 0) if checkout_weekday == 6 else time(12, 0)


def _build_body(message_type: str, booking: Booking) -> str:
    name = (booking.guest_name or "").split()[0] if booking.guest_name else "אורח"
    room = booking.room_name or ""
    checkin_str = booking.check_in.strftime("%d/%m/%Y") if booking.check_in else ""
    checkout_str = booking.check_out.strftime("%d/%m/%Y") if booking.check_out else ""
    code = booking.entry_code or "יישלח בנפרד"

    templates = {
        "confirmation": (
            f"שלום {name} 😊\n"
            f"ברכות! הזמנתך ל{room} אושרה.\n"
            f"כניסה: {checkin_str} | יציאה: {checkout_str}\n"
            f"נשמח לארח אתכם! 🏜️🌊\n"
            f"— Desert & Sea"
        ),
        "pre_arrival": (
            f"שלום {name}!\n"
            f"מזכירים — עוד יומיים ההגעה שלכם ל{room} 🎉\n"
            f"כניסה: {checkin_str}\n"
            f"יש שאלות? כאן בשבילכם!\n"
            f"— Desert & Sea"
        ),
        "entry_code": (
            f"שלום {name}!\n"
            f"הכל מוכן לקראתכם 🔑\n"
            f"קוד כניסה: *{code}*\n"
            f"נתראה היום!\n"
            f"— Desert & Sea"
        ),
        "checkout": (
            f"שלום {name}!\n"
            f"מקווים שנהניתם 🙏\n"
            f"תזכורת: יציאה עד {checkout_str}.\n"
            f"נשמח לראותכם שוב!\n"
            f"— Desert & Sea"
        ),
    }
    return templates.get(message_type, "")
