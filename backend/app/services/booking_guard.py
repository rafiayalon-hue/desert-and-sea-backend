"""
NEW (9.10.26) — שמירה על עקביות הזמנות מול המנעולים וההודעות.

רקע (אוקטובר 2026):
  * ליאת לסקה — שינתה תאריכים ב-Airbnb → MiniHotel יצר הזמנה חדשה (546) ולא
    שלח ביטול על המקורית (511). המקורית נשארה "פעילה", קיבלה הודעת הגעה וקוד.
  * איל יוסף — הועבר צימר (ים → מדבר). הקוד נשאר על מנעול ים.

מה יש כאן:
  supersede_duplicates(booking, db)
      הזמנה חדשה מאותו אורח (אותו טלפון) + אותו צימר + תאריכים חופפים →
      הישנה מבוטלת, הקוד שלה נמחק, ההודעות המתוזמנות שלה מבוטלות.
  sync_code_after_change(booking, db, old_room, old_ci, old_co)
      שינוי צימר → הקוד עובר למנעול החדש (אותו קוד) והישן נמחק.
      שינוי תאריכים בלבד → חלון התוקף במנעול מתעדכן.
  booking_issues(booking)
      רשימת בעיות להזמנה (חסר צימר / טלפון / קוד / סטטוס מייבוא).
  notify_owners(title, message)
      התראה לרפי ולאבישג דרך webhook של Home Assistant (אם הוגדר).
  detect_milk(text) / get_milk(booking) / set_milk(booking, milk)
      סוג החלב שהאורח ביקש — נשמר כשורה "חלב: X" בהערות ההזמנה
      (בלי שינוי בטבלה). נקלט אוטומטית מתשובת וואטסאפ לתזכורת של יומיים לפני.
"""
import re
import logging
import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, is_cancelled_status

logger = logging.getLogger(__name__)

# הזמנות שנכנסו מייבוא Excel ולא דרך ה-webhook — אין עליהן עדכוני ביטול אמינים
IMPORT_STATUSES = {"channel manager", "homepage", "הקצאה"}
# אחרי בדיקה ידנית ב-MiniHotel — כפתור בדשבורד מוסיף את הסימון להערות וההתראה נפסקת
VERIFIED_MARK = "[נבדק ב-MiniHotel]"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def norm_phone(p: str | None) -> str:
    p = "".join(ch for ch in (p or "") if ch.isdigit())
    if p.startswith("972"):
        p = "0" + p[3:]
    return p


def lock_set(room_name: str | None) -> set[int]:
    from app.integrations.ttlock import _resolve_lock_ids
    return set(_resolve_lock_ids(room_name or ""))


def _overlaps(a, b) -> bool:
    return a.check_in < b.check_out and b.check_in < a.check_out


async def notify_owners(title: str, message: str) -> None:
    """שולח התראה ל-HA (webhook) — HA מפיץ לשני הטלפונים.
    משתנה סביבה HA_WEBHOOK_URL, למשל:
      https://<nabu-casa-id>.ui.nabu.casa/api/webhook/dashboard_alert
    בלי המשתנה — רק לוג."""
    logger.warning("[OWNER_ALERT] %s — %s", title, message)
    url = os.getenv("HA_WEBHOOK_URL")
    if not url:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"title": title, "message": message}, timeout=10)
    except Exception as e:  # noqa: BLE001 — התראה לא אמורה להפיל שום תהליך
        logger.error("notify_owners failed: %s", e)


# ---------------------------------------------------------------------------
# (א) הזמנה שהוחלפה
# ---------------------------------------------------------------------------
async def supersede_duplicates(booking: Booking, db: AsyncSession) -> list[dict]:
    """מבטל הזמנות ישנות של אותו אורח שהוחלפו בהזמנה הנוכחית.
    תנאים (כולם): אותו טלפון (מנורמל), חפיפה בצימר (מנעול משותף), חפיפה בתאריכים,
    ההזמנה הישנה לא מבוטלת. הזמנה של אותו אורח לשני הצימרים בנפרד (כמו
    Carmel Vider / ליאת בסיס) לא נפגעת — אין מנעול משותף."""
    phone = norm_phone(booking.guest_phone)
    locks = lock_set(booking.room_name)
    if not phone or not locks or is_cancelled_status(booking.status):
        return []

    rows = (await db.execute(
        select(Booking).where(
            Booking.id != booking.id,
            Booking.check_in < booking.check_out,
            Booking.check_out > booking.check_in,
        )
    )).scalars().all()

    from app.scheduler import cancel_scheduled_jobs
    from app.integrations.ttlock import remove_passcode_after_checkout

    superseded = []
    for old in rows:
        if is_cancelled_status(old.status):
            continue
        if norm_phone(old.guest_phone) != phone:
            continue
        if not (lock_set(old.room_name) & locks) or not _overlaps(old, booking):
            continue

        cancel_scheduled_jobs(old.id)
        code_removed = False
        if old.ttlock_pwd_ids:
            try:
                code_removed = await remove_passcode_after_checkout(old, db)
            except Exception as e:  # noqa: BLE001
                logger.error("supersede: code removal failed for %s: %s", old.id, e)
        old.status = "cancelled"
        note = f"[אוטומטי] הוחלפה ע\"י הזמנה {booking.minihotel_id or booking.id}"
        old.notes = f"{old.notes}\n{note}" if old.notes else note
        db.add(old)
        superseded.append({
            "id": old.id, "minihotel_id": old.minihotel_id, "guest": old.guest_name,
            "check_in": old.check_in.isoformat(), "check_out": old.check_out.isoformat(),
            "code_removed": code_removed,
        })

    if superseded:
        await db.commit()
        lines = [f"{s['guest']}: הזמנה {s['minihotel_id']} ({s['check_in']}–{s['check_out']}) בוטלה"
                 for s in superseded]
        await notify_owners(
            "הזמנה הוחלפה — בוטלה אוטומטית",
            "\n".join(lines) + f"\nהחדשה: {booking.minihotel_id} "
            f"({booking.check_in}–{booking.check_out}, {booking.room_name}). לוודא ב-MiniHotel.",
        )
    return superseded


# ---------------------------------------------------------------------------
# (ג) שינוי צימר / תאריכים → עדכון המנעול
# ---------------------------------------------------------------------------
async def sync_code_after_change(booking: Booking, db: AsyncSession,
                                 old_room: str | None, old_ci, old_co) -> dict:
    """להפעיל אחרי commit של עדכון הזמנה. לא זורק חריגות."""
    result = {"moved": False, "window_updated": False, "error": None}
    if is_cancelled_status(booking.status) or not booking.ttlock_pwd_ids or not booking.entry_code:
        return result

    from app.integrations.ttlock import (
        assign_passcode_to_booking, remove_passcode_after_checkout, update_passcode_window,
    )
    try:
        if lock_set(old_room) != lock_set(booking.room_name):
            new_locks = lock_set(booking.room_name)
            code = booking.entry_code
            await remove_passcode_after_checkout(booking, db)
            if new_locks:
                await assign_passcode_to_booking(booking, db, code)
                result["moved"] = True
                await notify_owners(
                    "קוד הועבר למנעול אחר",
                    f"{booking.guest_name}: צימר {old_room} → {booking.room_name}. "
                    f"הקוד {code} הועבר והישן נמחק.",
                )
            else:
                await notify_owners(
                    "הזמנה בלי צימר — הקוד נמחק",
                    f"{booking.guest_name} ({booking.minihotel_id}): הצימר לא מזוהה "
                    f"('{booking.room_name}'). הקוד {code} נמחק — ליצור מחדש אחרי תיקון הצימר.",
                )
        elif booking.check_in != old_ci or booking.check_out != old_co:
            result["window_updated"] = await update_passcode_window(booking, db)
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
        logger.error("sync_code_after_change failed for %s: %s", booking.id, e)
        await notify_owners("שגיאה בעדכון קוד במנעול",
                            f"{booking.guest_name} ({booking.minihotel_id}): {str(e)[:150]}")
    return result


# ---------------------------------------------------------------------------
# (ד) בעיות בהזמנה
# ---------------------------------------------------------------------------
def booking_issues(b: Booking) -> list[str]:
    if is_cancelled_status(b.status):
        return []
    issues = []
    if not lock_set(b.room_name):
        issues.append("אין צימר")
    if not norm_phone(b.guest_phone):
        issues.append("אין טלפון")
    if not b.entry_code:
        issues.append("אין קוד כניסה")
    if (b.status or "").strip().lower() in IMPORT_STATUSES and VERIFIED_MARK not in (b.notes or ""):
        issues.append("נכנסה מייבוא — לוודא ב-MiniHotel שלא בוטלה")
    return issues


# ---------------------------------------------------------------------------
# (ה) סוג חלב — שורה "חלב: X" בהערות
# ---------------------------------------------------------------------------
# הסדר חשוב: "ללא לקטוז" לפני "רגיל", "חלב שקדים" לפני "בלי חלב" וכו'.
_MILK_RULES = [
    ("ללא לקטוז", ("לקטוז", "lactose")),
    ("סויה", ("סויה", "soy")),
    ("שקדים", ("שקד", "almond")),
    ("שיבולת שועל", ("שיבולת", "שועל", "oat")),
    ("אורז", ("אורז", "rice")),
    ("קוקוס", ("קוקוס", "coconut")),
    ("ללא", ("בלי חלב", "ללא חלב", "לא צריך", "לא צריכים", "no milk", "none")),
    ("רגיל", ("רגיל", "פרה", "3%", "1%", "regular", "cow", "normal")),
]
_MILK_LINE = re.compile(r"^חלב:\s*(.+)$", re.MULTILINE)


def detect_milk(text: str | None) -> str | None:
    t = (text or "").lower()
    for label, words in _MILK_RULES:
        if any(w in t for w in words):
            return label
    return None


def get_milk(b: Booking) -> str | None:
    m = _MILK_LINE.search(b.notes or "")
    return m.group(1).strip() if m else None


def set_milk(b: Booking, milk: str) -> None:
    line = f"חלב: {milk}"
    notes = b.notes or ""
    if _MILK_LINE.search(notes):
        b.notes = _MILK_LINE.sub(line, notes, count=1)
    else:
        b.notes = f"{notes}\n{line}" if notes else line
