from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Booking
from pydantic import BaseModel

router = APIRouter()


def normalize_phone(phone: str) -> str:
    """נרמול טלפון — מסיר רווחים, מקפים, קידומת בינלאומית"""
    p = phone.strip().replace("-", "").replace(" ", "")
    if p.startswith("+972"):
        p = "0" + p[4:]
    elif p.startswith("972"):
        p = "0" + p[3:]
    return p


@router.get("/lookup")
async def lookup_by_phone(
    phone: str = Query(..., description="טלפון לחיפוש"),
    db: AsyncSession = Depends(get_db),
):
    """
    זיהוי אורח לפי טלפון — מחזיר את כל ההזמנות + סיכום היסטוריה.
    משמש לפני שליחת WhatsApp ולזיהוי אורחים חוזרים.
    """
    normalized = normalize_phone(phone)

    # חיפוש לפי טלפון מנורמל וגם כפי שנשמר
    result = await db.scalars(
        select(Booking)
        .where(Booking.guest_phone != "")
        .where(Booking.guest_phone.isnot(None))
        .order_by(Booking.check_in)
    )
    all_bookings = result.all()

    # סינון לפי טלפון (עם נרמול)
    matches = [b for b in all_bookings if normalize_phone(b.guest_phone or "") == normalized]

    if not matches:
        return {
            "found": False,
            "phone": phone,
            "normalized": normalized,
            "visit_count": 0,
            "is_returning": False,
            "bookings": [],
        }

    # איסוף שמות שונים (זיהוי אותו אורח עם שמות שונים)
    names = list({b.guest_name for b in matches})

    # הזמנות פעילות בלבד (לא ביטולים)
    active = [b for b in matches if (b.status or "").lower() not in ("cancelled", "cancel")]

    last_visit = max((b.check_in for b in active), default=None)
    first_visit = min((b.check_in for b in active), default=None)

    # האם יש שמות שונים — דגל אזהרה
    multiple_names = len(names) > 1

    return {
        "found": True,
        "phone": phone,
        "normalized": normalized,
        "is_returning": len(active) > 1,
        "visit_count": len(active),
        "names_on_record": names,
        "multiple_names_warning": multiple_names,
        "first_visit": str(first_visit) if first_visit else None,
        "last_visit": str(last_visit) if last_visit else None,
        "bookings": [
            {
                "id": b.id,
                "guest_name": b.guest_name,
                "check_in": str(b.check_in),
                "check_out": str(b.check_out),
                "room_name": b.room_name,
                "status": b.status,
                "source": b.source,
            }
            for b in matches
        ],
    }


@router.get("/")
async def list_guests(
    returning_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    result = await db.scalars(select(Booking).order_by(Booking.guest_name))
    bookings = result.all()
    return bookings


@router.get("/{guest_id}")
async def get_guest(guest_id: int, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, guest_id)
    if not booking:
        raise HTTPException(status_code=404, detail="אורח לא נמצא")
    return booking


@router.patch("/{guest_id}/notes")
async def update_notes(
    guest_id: int, notes: str, db: AsyncSession = Depends(get_db)
):
    booking = await db.get(Booking, guest_id)
    if not booking:
        raise HTTPException(status_code=404, detail="אורח לא נמצא")
    booking.notes = notes
    await db.commit()
    return booking


class PhoneUpdate(BaseModel):
    phone: str


@router.patch("/by-name/phone")
async def update_phone_by_name(
    data: PhoneUpdate,
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """עדכון טלפון לפי שם אורח — מעדכן את כל ההזמנות עם אותו שם"""
    result = await db.scalars(
        select(Booking).where(Booking.guest_name == name)
    )
    bookings = result.all()
    if not bookings:
        raise HTTPException(status_code=404, detail=f"לא נמצא אורח בשם: {name}")
    for b in bookings:
        b.guest_phone = data.phone
    await db.commit()
    return {"updated": len(bookings), "name": name, "phone": data.phone}


@router.post("/upload-phones")
async def upload_phones(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """העלאת CSV עם עמודות name,phone — מעדכן טלפונים בכל ההזמנות לפי שם"""
    import io
    import csv
    contents = await file.read()
    text = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    updated_names = 0
    updated_bookings = 0
    not_found = []
    for row in reader:
        name  = (row.get("name")  or "").strip()
        phone = (row.get("phone") or "").strip()
        if not name or not phone:
            continue
        result = await db.scalars(
            select(Booking).where(Booking.guest_name == name)
        )
        bookings = result.all()
        if not bookings:
            not_found.append(name)
            continue
        for b in bookings:
            b.guest_phone = phone
        updated_names    += 1
        updated_bookings += len(bookings)
    await db.commit()
    return {
        "updated_names":    updated_names,
        "updated_bookings": updated_bookings,
        "not_found":        not_found,
    }
