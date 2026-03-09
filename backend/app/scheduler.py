"""
APScheduler — WhatsApp message scheduler.
Runs inside FastAPI process (no Redis/Celery needed).

Schedule:
  1. Confirmation   — triggered immediately on new booking (if phone exists)
  2. Pre-arrival    — 48h before check_in at 10:00
  3. Entry code     — day of check_in: 12:00 Sun-Fri, 14:00 Sat
  4. Checkout       — 2h before checkout_time (default: 12:00 / 14:00 Sat)
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
    Call this after a booking is created/updated.
    """
    if not booking.guest_phone:
        return

    phone = booking.guest_phone
    bid = booking.id

    # 2. Pre-arrival — 48h before check_in at 10:00
    pre_arrival_dt = datetime.combine(booking.check_in - timedelta(days=2), time(10, 0))
    _add_job(f"pre_arrival_{bid}", pre_arrival_dt, bid, "pre_arrival", phone, booking)

    # 3. Entry code — check_in day, 2h before checkin time
    checkin_time = _checkin_time(booking.check_in)
    entry_dt = datetime.combine(booking.check_in, checkin_time) - timedelta(hours=2)
    _add_job(f"entry_{bid}", entry_dt, bid, "entry_code", phone, booking)

    # 4. Checkout — 2h before checkout time
    checkout_time = _checkout_time(booking.check_in)  # based on arrival weekday
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
        await _send_if_not_sent(booking_id, message_type, phone, body, db)


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


def _checkin_time(d: date) -> time:
    """14:00 on Saturday, 12:00 otherwise (Sun-Fri in Israel = 0-5 weekday, Sat=6 in Python but isoweekday Sat=6)."""
    return time(16, 0) if d.isoweekday() == 6 else time(14, 0)


def _checkout_time(checkin: date) -> time:
    """14:00 if checked-in on Friday (checkout Saturday), 12:00 otherwise."""
    checkout_weekday = (checkin + timedelta(days=1)).isoweekday()
    return time(14, 0) if checkout_weekday == 6 else time(12, 0)


def _build_body(message_type: str, booking: Booking) -> str:
    """
    Build WhatsApp message body.
    Language detection: simple heuristic — extend as needed.
    """
    name = (booking.guest_name or "").split()[0] if booking.guest_name else "Guest"
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
