from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Booking
import logging

router = APIRouter()


def _norm(p: str) -> str:
    """נרמול טלפון — מסיר רווחים, מקפים, קידומת בינלאומית"""
    p = (p or "").strip().replace("-", "").replace(" ", "")
    if p.startswith("+972"):
        p = "0" + p[4:]
    elif p.startswith("972"):
        p = "0" + p[3:]
    return p


@router.post("/merge-by-phone")
async def merge_guests_by_phone(db: AsyncSession = Depends(get_db)):
    """
    סקריפט חד-פעמי — עובר על כל ההזמנות הקיימות ומסמן אורחים חוזרים.
    לא משנה נתונים — רק מוסיף is_returning_guest=True היכן שרלוונטי.
    בטוח להרצה חוזרת (idempotent).
    """
    result = await db.scalars(
        select(Booking)
        .where(Booking.guest_phone != "")
        .where(Booking.guest_phone.isnot(None))
        .order_by(Booking.check_in)
    )
    all_bookings = result.all()

    # קיבוץ לפי טלפון מנורמל
    phone_map: dict[str, list[Booking]] = {}
    for b in all_bookings:
        key = _norm(b.guest_phone or "")
        if not key:
            continue
        phone_map.setdefault(key, []).append(b)

    marked = 0
    multi_name_warnings = []

    for phone, bookings in phone_map.items():
        active = [
            b for b in bookings
            if (b.status or "").lower() not in ("cancelled", "cancel")
        ]

        if len(active) <= 1:
            continue  # אורח חדש — לא מסמנים

        # בדיקת שמות שונים
        names = {b.guest_name for b in active}
        if len(names) > 1:
            multi_name_warnings.append({
                "phone": phone,
                "names": list(names),
                "booking_ids": [b.id for b in active],
            })

        # סימון כל ההזמנות (מלבד הראשונה) כ-returning
        active_sorted = sorted(active, key=lambda b: b.check_in)
        for b in active_sorted[1:]:  # הראשונה = ביקור ראשון, השאר = חוזרים
            if not getattr(b, "is_returning_guest", False):
                b.is_returning_guest = True
                marked += 1

    await db.commit()

    logging.info(f"[MERGE] marked={marked}, warnings={len(multi_name_warnings)}")

    return {
        "status": "done",
        "total_phones_with_history": len([p for p, b in phone_map.items() if len(b) > 1]),
        "bookings_marked_returning": marked,
        "multi_name_warnings": multi_name_warnings,  # לבדיקה ידנית
    }
