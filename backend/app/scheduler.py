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

הערה (9.7.26): כל 4 סוגי ההודעות עוברות עכשיו דרך WhatsApp Content
Templates מאושרים (ראו app/integrations/whatsapp.py, CONTENT_SIDS) במקום
טקסט חופשי — נדרש ע"י Meta לכל הודעה שהעסק יוזם. _build_body עדיין קיימת
ומשמשת לתיעוד קריא בעברית ב-MessageLog.body, אבל היא לא מה שנשלח בפועל.

הערה (9.7.26 #2): תבנית "entry_code" לא מכילה יותר את הקוד עצמו בגוף
ההודעה — מטא דוחה אוטומטית כל תבנית Utility עם ערך שנראה כמו קוד אימות
(3 ניסיונות נדחו). הפתרון: כפתור CTA URL בתבנית שמוביל לעמוד באתר
הציבורי, שם האורח *רואה* את הקוד (לא מקבל אותו בטקסט). המשתנה שנשלח
לתבנית הוא לכן טוקן (CheckinToken) ולא booking.entry_code.

NEW (30.9.26) — גיבוי SMS (019) כש-WhatsApp נכשל:
  * כל הודעה מנסה קודם WhatsApp. נכשל + SMS מוגדר → אותה הודעה ב-SMS
    (נוסחים ב-app/integrations/sms_texts.py). MessageLog.channel = 'sms'.
  * קוד כניסה ב-SMS יוצא רק מ-10:00 ביום הכניסה (לא ביום ההזמנה).
    ה-reconciliation משלים אותו בבוקר יום הכניסה.
  * תיקון: הודעת יציאה נשלחת רק עד שעת היציאה עצמה. קודם ה-reconciliation
    ניסה שוב עד 7 ימים אחרי — אורחים שעזבו היו מקבלים "תודה" באיחור.
  * תיקון: תזכורת 48h אבדה בכל deploy (job בזיכרון). ה-reconciliation
    משלים אותה עכשיו.
  * backfill_missing_confirmations — השלמה חד-פעמית של אישורי הזמנה.
"""
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.integrations.whatsapp import send_whatsapp_template
from app.integrations.sms import SmsError, send_sms, sms_enabled
from app.integrations import sms_texts
from app.models import Booking, MessageLog, is_cancelled_status
from app.models.checkin_token import CheckinToken

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Jerusalem")
ENTRY_CODE_SMS_HOUR = time(10, 0)   # קוד כניסה ב-SMS — מ-10:00 ביום הכניסה
BUSINESS_PHONE = "052-3730377"

scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")


def _now() -> datetime:
    """שעון ישראל, naive — תואם ל-datetime.combine(...) בשאר הקובץ."""
    return datetime.now(TZ).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Public helpers — called from webhook / other routes
# ---------------------------------------------------------------------------

async def trigger_confirmation(booking: Booking, db: AsyncSession):
    """Send confirmation immediately (message type 1)."""
    if not booking.guest_phone:
        logger.info(f"Booking {booking.id}: no phone, skipping confirmation")
        return
    await _send_if_not_sent(booking.id, "confirmation", booking.guest_phone, booking, db)


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
        if is_cancelled_status(booking.status):
            return
        if not booking.guest_phone or not booking.check_in or not booking.check_out:
            return
        if booking.entry_code:
            return

        from app.integrations.ttlock import assign_passcode_to_booking
        code = await assign_passcode_to_booking(booking, db)
        if code:
            logger.info(f"Booking {booking_id}: entry code {code} created")
            # ה-booking בזיכרון עדיין לא כולל את entry_code שזה עתה נכתב
            # ב-DB דרך assign_passcode_to_booking — מרעננים כדי שה-variables
            # שנבנים ל-Content Template יכללו את הקוד האמיתי, לא ריק.
            await db.refresh(booking)
            # יוצר/מוצא טוקן לעמוד "פרטי הכניסה שלי" באתר הציבורי —
            # זה מה שיישלח לתבנית ה-WhatsApp, לא הקוד עצמו.
            await _get_or_create_checkin_token(booking, db)
            await _send_if_not_sent(booking.id, "entry_code", booking.guest_phone, booking, db)
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
    now = _now()

    # 1. Entry code — מיד
    await create_and_send_entry_code(bid, db)

    # 2. Pre-arrival — 48h before check_in at 10:00
    #    מדלגים אם ההזמנה נכנסה פחות מ-48 שעות לפני הכניסה
    pre_arrival_dt = _pre_arrival_dt(booking)
    hours_to_checkin = (datetime.combine(booking.check_in, time(14, 0)) - now).total_seconds() / 3600

    if hours_to_checkin > 48:
        _add_job(f"pre_arrival_{bid}", pre_arrival_dt, bid, "pre_arrival", phone)
    else:
        logger.info(f"Booking {bid}: skipping pre_arrival — only {hours_to_checkin:.1f}h to check-in")

    # 3. Checkout — 2h before checkout_time
    checkout_dt = _checkout_dt(booking) - timedelta(hours=2)
    _add_job(f"checkout_{bid}", checkout_dt, bid, "checkout", phone)


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

async def _get_or_create_checkin_token(booking: Booking, db: AsyncSession) -> str:
    """
    מחזיר טוקן קיים לעמוד 'פרטי הכניסה שלי' עבור ההזמנה, או יוצר חדש
    אם עוד אין. הטוקן תקף עד יום ה-checkout (ראו app/models/checkin_token.py).
    """
    result = await db.execute(
        select(CheckinToken).where(CheckinToken.booking_id == booking.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing.token

    new_token = CheckinToken(
        booking_id=booking.id,
        token=CheckinToken.generate_token(),
        expires_at=booking.check_out,
    )
    db.add(new_token)
    await db.flush()
    logger.info(f"Booking {booking.id}: checkin token created")
    return new_token.token


def _add_job(job_id: str, run_at: datetime, booking_id: int,
             message_type: str, phone: str):
    now = _now()
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
    await _get_or_create_checkin_token(booking, db)
    await _send_if_not_sent(booking.id, "entry_code", booking.guest_phone, booking, db)


async def _send_scheduled(booking_id: int, message_type: str, phone: str,
                          send_message: bool = True):
    """Job function — opens its own DB session, ומרענן את ה-booking מה-DB
    בזמן ריצה בפועל (לא לוקח נתונים ישנים מרגע התזמון).
    send_message=False → רק מחיקת קוד TTLock ביציאה, בלי הודעה."""
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
        if is_cancelled_status(booking.status):
            logger.info(f"Booking {booking_id}: cancelled, skipping {message_type}")
            return

        # לאחר שליחת הודעת יציאה — מחק קוד TTLock
        if message_type == "checkout":
            await _delete_ttlock_after_checkout(booking_id, db)
        if send_message:
            await _send_if_not_sent(booking_id, message_type, phone, booking, db)


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


def _sms_allowed_now(message_type: str, booking: Booking) -> bool:
    """קוד כניסה ב-SMS רק מ-10:00 ביום הכניסה; שאר ההודעות — מיד."""
    if message_type != "entry_code":
        return True
    if not booking.check_in:
        return False
    return _now() >= datetime.combine(booking.check_in, ENTRY_CODE_SMS_HOUR)


async def _send_if_not_sent(booking_id: int, message_type: str,
                             phone: str, booking: Booking, db: AsyncSession):
    """
    שולח רק אם כבר יש רשומה בסטטוס 'sent' — לא סתם "יש רשומה" (זה היה
    באג: ניסיון כושל, למשל Twilio לא מחובר, היה מסמן את ההודעה כ"טופלה"
    לצמיתות; גם אחרי שTwilio יחובר ההודעה לא הייתה נשלחת לעולם). אם יש
    רשומה קודמת שנכשלה — מעדכנים אותה בניסיון הזה במקום ליצור כפולה.

    סדר: WhatsApp Content Template → אם נכשל ו-SMS מוגדר → SMS (019).
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

    body = _build_body(message_type, booking)
    variables = await _build_variables(message_type, booking, db)
    channel = "whatsapp"

    try:
        sid = send_whatsapp_template(phone, message_type, variables)
        status = "sent"
    except Exception as e:
        logger.error(f"WhatsApp send failed for booking {booking_id}: {e}")
        sid = None
        status = "failed"

    # --- גיבוי SMS ---
    if status == "failed" and sms_enabled() and _sms_allowed_now(message_type, booking):
        try:
            sms_body = await build_sms_text(message_type, booking, db, phone)
            shipment = await send_sms(phone, sms_body, ref=f"{booking_id}-{message_type}")
            sid = f"019:{shipment}"
            status = "sent"
            channel = "sms"
            body = sms_body
        except SmsError as e:
            logger.error(f"SMS fallback failed for booking {booking_id} ({message_type}): {e}")

    if existing:
        existing.body = body
        existing.status = status
        existing.twilio_sid = sid
        existing.channel = channel
        if status == "sent":
            existing.sent_at = datetime.utcnow()
        db.add(existing)
    else:
        log = MessageLog(
            booking_id=booking_id,
            phone=phone,
            message_type=message_type,
            body=body,
            status=status,
            twilio_sid=sid,
            channel=channel,
            sent_at=datetime.utcnow() if status == "sent" else None,
        )
        db.add(log)

    await db.commit()
    logger.info(f"Booking {booking_id}: {message_type} → {status} ({channel})")


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


def _booking_checkout_time(booking: Booking) -> time:
    """שעת היציאה בפועל: checkout_time מההזמנה (עזיבה מאוחרת) או ברירת מחדל.
    הערה: ברירת המחדל נשארת לפי check_out (יום היציאה) — כמו בקוד המקורי
    הקריאה הייתה _checkout_time(booking.check_in), שנראה כמו טעות."""
    if booking.checkout_time:
        return _parse_time(booking.checkout_time)
    return _checkout_time(booking.check_out)


def _checkout_dt(booking: Booking) -> datetime:
    return datetime.combine(booking.check_out, _booking_checkout_time(booking))


def _pre_arrival_dt(booking: Booking) -> datetime:
    return datetime.combine(booking.check_in - timedelta(days=2), time(10, 0))


def _display_room_name(raw_room_name: str) -> str:
    """
    NEW (17.7.26): שם החדר כפי שמוצג לאורח בהודעות בפועל — לא הערך הגולמי
    מה-DB, שיכול להכיל "Sesert" (שגיאת כתיב היסטורית ממיניהוטל/יבוא ישן,
    ראו גם _resolve_lock_ids ב-ttlock.py ו-_normalise_room ב-webhook.py)
    או שמות אנגליים גולמיים כמו "Sea"/"Desert"/"Des_Sea". בלעדיה, אורח
    היה מקבל הודעה עם "הזמנתך ל-Sesert אושרה" — בדיוק הבאג שדווח.
    """
    normalised = (raw_room_name or "").strip().lower().replace(" ", "")
    if "des_sea" in normalised:
        return "מדבר וים"
    if "sesert" in normalised or "desert" in normalised or "מדבר" in (raw_room_name or ""):
        return "מדבר"
    if "sea" in normalised or "ים" in (raw_room_name or ""):
        return "ים"
    return raw_room_name or ""


def _build_body(message_type: str, booking: Booking) -> str:
    """טקסט קריא בעברית, נשמר ב-MessageLog לצורך תיעוד/הצגה בדשבורד בלבד
    — זה לא מה שנשלח בפועל לאורח (ראו _send_if_not_sent). כאן עדיין מציגים
    את הקוד עצמו — זה תיעוד פנימי לדשבורד, לא הודעת WhatsApp."""
    name = (booking.guest_name or "").split()[0] if booking.guest_name else "אורח"
    room = _display_room_name(booking.room_name)
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
            f"היי {name}! מחכים לכם בהתרגשות ⛺\n"
            f"(תיעוד פנימי בלבד — הקוד עצמו לא נשלח יותר בטקסט ל-WhatsApp,"
            f" האורח רואה אותו בקישור. קוד לצפייה בדשבורד: {code})\n"
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


def _is_israeli(phone: str) -> bool:
    p = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    return p.startswith("0") or p.startswith("972") or p.startswith("+972")


async def build_sms_text(message_type: str, booking: Booking, db: AsyncSession,
                         phone: str | None = None) -> str:
    """הטקסט המלא לאורח (SMS / כפתור 'שלח בוואטסאפ'). עברית לישראלי, אנגלית לאחר."""
    lang = "he" if _is_israeli(phone or booking.guest_phone or "") else "en"
    first = (booking.guest_name or "").split()[0] if booking.guest_name else ""
    room = _display_room_name(booking.room_name)

    link = ""
    if message_type == "entry_code" and settings.checkin_page_url:
        token = await _get_or_create_checkin_token(booking, db)
        label = "מפה והוראות" if lang == "he" else "Map & directions"
        link = f"{label}: {settings.checkin_page_url.replace('{token}', token)}\n"

    fields = {
        "name": first or ("אורח" if lang == "he" else "guest"),
        "room": sms_texts.room_phrase_he(room) if lang == "he" else room,
        "checkin": booking.check_in.strftime("%d/%m") if booking.check_in else "",
        "checkout": booking.check_out.strftime("%d/%m") if booking.check_out else "",
        "checkout_time": _booking_checkout_time(booking).strftime("%H:%M") if booking.check_out else "",
        "code": booking.entry_code or "",
        "arrival": sms_texts.ARRIVAL_NOTE_HE if lang == "he" else sms_texts.ARRIVAL_NOTE_EN,
        "link": link,
        "phone": BUSINESS_PHONE,
    }
    template = sms_texts.TEXTS[lang].get(message_type, "")
    return template.format(**fields).replace("\n\n", "\n").strip()


async def _build_variables(message_type: str, booking: Booking, db: AsyncSession) -> dict:
    """
    בונה את ה-content_variables ({{1}}, {{2}}, ...) לכל תבנית מאושרת,
    בהתאמה מדויקת לסדר המשתנים שהוגדר בכל תבנית ב-Twilio Content
    Template Builder (ראו app/integrations/whatsapp.py, CONTENT_SIDS).

    entry_code: {{2}} הוא כעת טוקן לכפתור ה-URL (עמוד באתר הציבורי),
    לא הקוד עצמו — ראו הערת 9.7.26 #2 בראש הקובץ.
    """
    name = (booking.guest_name or "").split()[0] if booking.guest_name else "אורח"
    room = _display_room_name(booking.room_name)
    checkin_str = booking.check_in.strftime("%d/%m/%Y") if booking.check_in else ""
    checkout_str = booking.check_out.strftime("%d/%m/%Y") if booking.check_out else ""

    if message_type == "entry_code":
        token = await _get_or_create_checkin_token(booking, db)
        return {"1": name, "2": token}

    variables = {
        "confirmation": {"1": name, "2": room, "3": checkin_str, "4": checkout_str},
        "pre_arrival": {"1": name, "2": room, "3": checkin_str},
        "checkout": {"1": name, "2": checkout_str},
    }
    return variables.get(message_type, {})


# ---------------------------------------------------------------------------
# Reconciliation — safety net for the deploy-wipes-memory problem
# ---------------------------------------------------------------------------

@scheduler.scheduled_job("interval", minutes=30, id="reconcile_pending_jobs")
async def reconcile_pending_jobs():
    await _run_reconciliation()


async def run_reconciliation_now():
    """נקרא פעם אחת מ-main.py מיד אחרי scheduler.start()."""
    await _run_reconciliation()


async def _send_for_booking(booking_id: int, message_type: str):
    """שולח (אם לא נשלח) עם session מבודד — ל-reconciliation."""
    async with AsyncSessionLocal() as db:
        booking = await db.get(Booking, booking_id)
        if booking is None or is_cancelled_status(booking.status) or not booking.guest_phone:
            return
        await _send_if_not_sent(booking.id, message_type, booking.guest_phone, booking, db)


def _created_local(booking: Booking) -> datetime | None:
    """created_at נשמר ב-UTC (datetime.utcnow) → שעון ישראל."""
    created = getattr(booking, "created_at", None)
    if created is None:
        return None
    return created.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ).replace(tzinfo=None)


async def _run_reconciliation():
    now = _now()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Booking))
        bookings = result.scalars().all()

    for booking in bookings:
        if is_cancelled_status(booking.status):
            # NEW (20.9.26): הזמנה מבוטלת שעדיין מחזיקה קוד פעיל על המנעול
            # (שהייה שטרם הסתיימה) — מוחקים את הקוד. בלי זה, אורח שביטל
            # נשאר עם קוד תקף לדלת. לא נשלחת שום הודעה.
            if booking.ttlock_pwd_ids and booking.check_out and booking.check_out >= now.date():
                try:
                    from app.integrations.ttlock import remove_passcode_after_checkout
                    async with AsyncSessionLocal() as db2:
                        fresh = await db2.get(Booking, booking.id)
                        if fresh is not None and fresh.ttlock_pwd_ids:
                            ok = await remove_passcode_after_checkout(fresh, db2)
                            logger.info(f"Reconcile: removed passcode of cancelled booking {booking.id} (ok={ok})")
                except Exception as e:
                    logger.error(f"Reconcile: failed removing passcode of cancelled booking {booking.id}: {e}")
            continue
        if not booking.guest_phone or not booking.check_in or not booking.check_out:
            continue

        try:
            # --- קוד כניסה: רשת ביטחון — אם עדיין חסר, וההזמנה עדיין
            #     בתוך חלון השהייה (לא נגמרה), ננסה ליצור+לשלוח שוב.
            if not booking.entry_code and now.date() <= booking.check_out:
                await create_and_send_entry_code(booking.id)

            # --- NEW (30.9.26): הודעת קוד שלא נשלחה (WhatsApp נפל) —
            #     מ-10:00 ביום הכניסה ועד היציאה. _send_if_not_sent מדלג אם נשלחה.
            elif (
                booking.entry_code
                and datetime.combine(booking.check_in, ENTRY_CODE_SMS_HOUR) <= now < _checkout_dt(booking)
            ):
                await _send_for_booking(booking.id, "entry_code")

            # --- NEW (30.9.26): תזכורת 48h שאבדה ב-deploy. רק אם ההזמנה
            #     נכנסה יותר מ-48h לפני הכניסה (כמו הכלל המקורי), ו-15 דק'
            #     אחרי הזמן המתוכנן כדי לא להתנגש ב-job עצמו.
            pre_dt = _pre_arrival_dt(booking)
            created = _created_local(booking)
            checkin_dt = datetime.combine(booking.check_in, time(14, 0))
            if (
                created is not None
                and created < checkin_dt - timedelta(hours=48)
                and pre_dt + timedelta(minutes=15) <= now < datetime.combine(booking.check_in, ENTRY_CODE_SMS_HOUR)
            ):
                await _send_for_booking(booking.id, "pre_arrival")

            # --- יציאה: מוחק קוד (אם קיים). הודעה — רק עד שעת היציאה עצמה.
            #     (תיקון 30.9.26: קודם נשלח עד 7 ימים אחרי — "תודה" לאורחים שכבר עזבו.)
            checkout_at = _checkout_dt(booking)
            checkout_due_at = checkout_at - timedelta(hours=2)
            recent_enough = booking.check_out >= (now.date() - timedelta(days=7))
            if now >= checkout_due_at and recent_enough:
                await _send_scheduled(
                    booking.id, "checkout", booking.guest_phone,
                    send_message=now < checkout_at,
                )
        except Exception as e:
            logger.error(f"Reconcile: error processing booking {booking.id}: {e}")


# ---------------------------------------------------------------------------
# Backfill — השלמה חד-פעמית של אישורי הזמנה שלא נשלחו (30.9.26)
# ---------------------------------------------------------------------------

async def backfill_missing_confirmations(days: int = 14, dry_run: bool = True) -> list[dict]:
    """
    הזמנות שנכנסו ב-`days` הימים האחרונים, עוד לא הגיעו, לא מבוטלות,
    ולא קיבלו אישור הזמנה → שולח אישור (WhatsApp, ואם נכשל SMS).
    קוד כניסה לא נשלח כאן — הוא יוצא אוטומטית ב-10:00 ביום הכניסה.
    dry_run=True → רק מחזיר רשימה, לא שולח כלום.
    """
    now = _now()
    since = now - timedelta(days=days)
    out = []

    async with AsyncSessionLocal() as db:
        bookings = (await db.execute(
            select(Booking).where(Booking.check_in >= now.date())
        )).scalars().all()
        sent_ids = set((await db.execute(
            select(MessageLog.booking_id).where(
                MessageLog.message_type == "confirmation",
                MessageLog.status == "sent",
            )
        )).scalars().all())

    for b in bookings:
        if is_cancelled_status(b.status) or not b.guest_phone or b.id in sent_ids:
            continue
        created = _created_local(b) or getattr(b, "synced_at", None)
        if created is None or created < since:
            continue
        row = {
            "id": b.id, "guest": b.guest_name, "phone": b.guest_phone,
            "room": _display_room_name(b.room_name),
            "check_in": b.check_in.isoformat(), "created": created.isoformat(timespec="minutes"),
        }
        if not dry_run:
            await _send_for_booking(b.id, "confirmation")
            async with AsyncSessionLocal() as db:
                log = (await db.execute(select(MessageLog).where(
                    MessageLog.booking_id == b.id, MessageLog.message_type == "confirmation",
                ))).scalar_one_or_none()
                row["result"] = f"{log.status} ({log.channel})" if log else "no log"
        out.append(row)
    return out
