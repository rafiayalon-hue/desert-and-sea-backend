"""
קמפיינים — כלים לפנייה יזומה לאורחים (לא הודעות אוטומטיות דרך Twilio,
כי הודעות שיווק דורשות תבנית Marketing מאושרת שאין לנו עדיין — ראו
השיחה מ-17.7.26). המטרה: לרכז רשימה נגישה לפנייה אישית ידנית, מהטלפון
של רפי/אבישג עצמם.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking

router = APIRouter()


def _normalize_phone(phone: str) -> str:
    p = (phone or "").strip().replace("-", "").replace(" ", "")
    if p.startswith("+972"):
        p = "0" + p[4:]
    elif p.startswith("972"):
        p = "0" + p[3:]
    return p


@router.get("/winback")
async def winback_list(months_back: int = 12, db: AsyncSession = Depends(get_db)):
    """
    אורחים ש: יצאו בעבר (עד שנה אחורה כברירת מחדל), ההזמנה לא בוטלה,
    יש להם טלפון או מייל, ו-**אין** להם שום הזמנה עתידית קיימת (לא
    לפנות למי שכבר הזמין קדימה — לפי הדרישה המפורשת).
    """
    today = date.today()
    cutoff = today - timedelta(days=months_back * 30)

    all_result = await db.execute(select(Booking))
    all_bookings = all_result.scalars().all()

    def is_cancelled(b):
        return "cancel" in (b.status or "").lower()

    # מפתחות (טלפון מנורמל, מייל) של כל מי שיש לו הזמנה עתידית — נפסול
    # אותם מהרשימה גם אם יש להם גם שהות עבר.
    future_phones = set()
    future_emails = set()
    for b in all_bookings:
        if b.check_in and b.check_in >= today and not is_cancelled(b):
            if b.guest_phone:
                future_phones.add(_normalize_phone(b.guest_phone))
            if b.guest_email:
                future_emails.add(b.guest_email.strip().lower())

    # מועמדים: שהות עבר בטווח, לא מבוטלת, יש דרך ליצור קשר
    candidates = []
    for b in all_bookings:
        if not b.check_out or b.check_out >= today or b.check_out < cutoff:
            continue
        if is_cancelled(b):
            continue
        phone_norm = _normalize_phone(b.guest_phone) if b.guest_phone else None
        email_norm = b.guest_email.strip().lower() if b.guest_email else None
        if not phone_norm and not email_norm:
            continue
        if phone_norm and phone_norm in future_phones:
            continue
        if email_norm and email_norm in future_emails:
            continue
        candidates.append(b)

    # דה-דופליקציה — לפי טלפון קודם, מייל כ-fallback (כמו ב-useGuests.js
    # בפרונט) — שומרים רק את השהות האחרונה ביותר לכל אורח ייחודי.
    dedup: dict[str, Booking] = {}
    for b in sorted(candidates, key=lambda x: x.check_out):
        key = _normalize_phone(b.guest_phone) if b.guest_phone else f"email:{b.guest_email.strip().lower()}"
        dedup[key] = b  # הכי מאוחר דורס (בזכות המיון)

    result = [
        {
            "guest_name": b.guest_name,
            "phone": b.guest_phone,
            "email": b.guest_email,
            "last_checkout": b.check_out.isoformat() if b.check_out else None,
            "last_room": b.room_name,
        }
        for b in dedup.values()
    ]
    result.sort(key=lambda r: r["last_checkout"] or "", reverse=True)
    return result
