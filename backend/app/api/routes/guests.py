from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Booking
from pydantic import BaseModel

router = APIRouter()


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
