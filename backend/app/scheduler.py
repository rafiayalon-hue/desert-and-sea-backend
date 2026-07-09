"""
APScheduler — WhatsApp message scheduler.
Runs inside FastAPI process (no Redis/Celery needed).

Schedule:
  1. Confirmation   — triggered immediately on new booking (if phone exists)
  2. Entry code     — created + sent IMMEDIATELY on new booking (not delayed).
                       Safe to do early: TTLock codes are created as "period"
                       type — the lock itself enforces the check_in/check_out
                       window physically, so an early-created code still can't
                       open the door before check_in.
  3. Pre-arrival    — 48h before check_in at 10:00  ← מדולג אם פחות מ-48h
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
from app.integrations.whatsapp import send_whatsapp, send_whatsapp_with_map
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


async def create_and_send_entry_code(booking_id: int, db: AsyncSession | None = None):
    """
    יוצר קוד כניסה ושולח הודעת WhatsApp — נקרא מיד עם קבלת ההזמנה
    (מ-schedule_booking_messages), וגם כרשת ביטחון מ-reconciliation.

    אם db לא סופק — פותח session משלו (למקרה של קריאה עצמאית, כמו
    מ-reconciliation שרץ על כמה הזמנות ברצף וצריך session מבודד לכל אחת).

    אידמפוטנטי לגמרי: לא עושה כלום אם ההזמנה בוטלה, אין טלפון, או שכבר
    יש entry_code (לא ייצור קוד כפול על המנעול).
    """
    own_session = db is None
    if own_session:
        db = AsyncSessionLocal()
    try:
        result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if booking is None:
            return
        if (booking.status or "").strip().lower() == "cancelled":
            return
        if not booking.guest_phone or not booking.check_in or not booking.check_out:
            return
        if booking.entry_code:
            return

        from app.integrations.ttlock import assign_passcode_to_booking
        code = await assign_passcode_to_booking(booking, db)
        if code:
            logger.info(f"Booking {booking_id}: entry code {code} created")
            await _send_if_not_sent(booking.id, "entry_code", booking.guest_phone,
                                     _build_body("entry_code", booking), db)
    except Exception as e:
        logger.error(f"create_and_send_entry_code error for booking {booking_id}: {e}")
    finally:
        if own_session:
            await db.close()


async def schedule_booking_messages(booking: Booking, db: AsyncSession):
    """
    Register timed messages (pre_arrival, checkout) for a booking, and
    create+send the entry code immediately (no longer delayed/scheduled).

    Logic:
    - Entry code: מיד, בבת אחת עם קריאת הפונקציה הזו
    - Pre-arrival (48h before): נשלח רק אם יש יותר מ-48 שעות לכניסה
    - Checkout: תמיד מתוזמן (אם בעתיד)
    """
    if not booking.guest_phone or not booking.check_in:
        return

    phone = booking.guest_phone
    bid = booking.id
    now = datetime.now()

    # 1. Entry code — מיד
    await create_and_send_entry_code(bid, db)

    # 2. Pre-arrival — 48h before check_in at 10:00
    #    מדלגים אם ההזמנה נכנסה פחות מ-48 שעות לפני הכניסה
    pre_arrival_dt = datetime.combine(booking.check_in - timedelta(days=2), time(10, 0))
    hours_to_checkin = (datetime.combine(booking.check_in, time(14, 0)) - now).total_seconds() / 3600

    if hours_to_checkin > 48:
        _add_job(f"pre_arrival_{bid}", pre_arrival_dt, bid, "pre_arrival", phone, booking)
    else:
        logger.info(f"Booking {bid}: skipping pre_arrival — only {hours_to_checkin:.1f}h to check-in")

    # 3. Checkout — 2h before checkout_time
    checkout_time = _parse_time(booking.checkout_time) if booking.checkout_time else _checkout_time(booking.check_in)
    checkout_dt = datetime.combine(booking.check_out, checkout_time) - timedelta(hours=2)
    _add_job(f"checkout_{bid}", checkout_dt, bid, "checkout", phone, booking)


def cancel_scheduled_jobs(booking_id: int):
    """
    מבטל jobs מתוזמנים (pre_arrival / checkout) עבור הזמנה — נקרא כשמתקבל
    reservation.cancelled. לא זורק שגיאה אם job לא קיים (כבר רץ, או שאבד
    בדיפלוי הקודם). קוד כניסה שכבר נוצר בפועל לא מטופל כאן — ראו
    webhook.py, שקורא בנפרד ל-remove_passcode_after_checkout במקרה ביטול.
    """
    for prefix in ("pre_arrival", "checkout"):
        job_id = f"{prefix}_{booking_id}"
        try:
            scheduler.remove_job(job_id)
            logger.info(f"Cancelled job {job_id} (booking cancelled)")
        except Exception:
            pass


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


async def send_entry_code_now(booking: Booking, db: AsyncSession):
    """
    נקרא מ-locks.py אחרי אישור/יצירה ידניים (assign-code) — שולח את הודעת
    קוד הכניסה עכשיו (מניח ש-booking.entry_code כבר נוצר בפועל ב-TTLock).
    אידמפוטנטי דרך _send_if_not_sent (MessageLog) — קריאה כפולה לא
    תשלח הודעה כפולה. לא נוגע ב-jobs מתוזמנים אחרים (pre_arrival/checkout)
    — אלה נשארים כרגיל, קוד הכניסה כבר לא מתוזמן בכלל.
    """
    await _send_if_not_sent(booking.id, "entry_code", booking.guest_phone,
                             _build_body("entry_code", booking), db)


async def _send_scheduled(booking_id: int, message_type: str, phone: str, body: str):
    """Job function — opens its own DB session."""
    async with AsyncSessionLocal() as db:
        # הגנה: אם ההזמנה בוטלה בין התזמון לבין הריצה בפועל — לא יוצרים
        # קוד TTLock ולא שולחים הודעה בכלל. חשוב במיוחד כי jobs בזיכרון
        # לא שורדים דיפלוי (ראו הערה למעלה) — אם job "פספס" ביטול כי הוא
        # נוצר מחדש ע"י reconciliation, ההגנה הזו היא קו ההגנה האחרון.
        result = await db.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()
        if booking is None:
            logger.info(f"Booking {booking_id}: not found, skipping {message_type}")
            return
        if (booking.status or "").strip().lower() == "cancelled":
            logger.info(f"Booking {booking_id}: cancelled, skipping {message_type}")
            return

        # לאחר שליחת הודעת יציאה — מחק קוד TTLock
        if message_type == "checkout":
            await _delete_ttlock_after_checkout(booking_id, db)
        await _send_if_not_sent(booking_id, message_type, phone, body, db)


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
    """
    שולח רק אם כבר יש רשומה בסטטוס 'sent' — לא סתם "יש רשומה" (זה היה
    באג: ניסיון כושל, למשל Twilio לא מחובר, היה מסמן את ההודעה כ"טופלה"
    לצמיתות; גם אחרי שTwilio יחובר ההודעה לא הייתה נשלחת לעולם). אם יש
    רשומה קודמת שנכשלה — מעדכנים אותה בניסיון הזה במקום ליצור כפולה.
    """
    existing_result = await db.execute(
        select(MessageLog).where(
            MessageLog.booking_id == booking_id,
            MessageLog.message_type == message_type,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing and existing.status == "sent":
        logger.info(f"Booking {booking_id}: {message_type} already sent, skipping")
        return

    try:
        if message_type == "entry_code":
            sid = send_whatsapp_with_map(phone, body)
        else:
            sid = send_whatsapp(phone, body)
        status = "sent"
    except Exception as e:
        logger.error(f"WhatsApp send failed for booking {booking_id}: {e}")
        sid = None
        status = "failed"

    if existing:
        existing.body = body
        existing.status = status
        existing.twilio_sid = sid
        db.add(existing)
    else:
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
    """כניסה תמיד 14:00."""
    return time(14, 0)


def _checkout_time(checkout: date) -> time:
    """יציאה: 14:00 בשבת, 12:00 בכל יום אחר."""
    return time(14, 0) if checkout.isoweekday() == 6 else time(12, 0)


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


# ---------------------------------------------------------------------------
# Reconciliation — safety net for the deploy-wipes-memory problem
# ---------------------------------------------------------------------------

@scheduler.scheduled_job("interval",
