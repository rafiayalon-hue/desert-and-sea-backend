"""
MiniHotel Webhook handler.
Receives room.occupancy.updated events from MiniHotel and upserts bookings into DB.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking
from app.scheduler import trigger_confirmation, schedule_booking_messages

router = APIRouter()


class WebhookRoom(BaseModel):
    roomNumber: str | None = None
    guestFirstName: str | None = None
    guestLastName: str | None = None
    guestPhone: str | None = None
    checkIn: str | None = None
    checkOut: str | None = None
    occupied: bool = False


class WebhookPayload(BaseModel):
    reservationNumber: str | None = None
    status: str | None = None
    rooms: list[WebhookRoom] = []
    timestamp: str | None = None
    guestPhone: str | None = None
    checkIn: str | None = None
    checkOut: str | None = None
    totalPrice: float | None = None


class MiniHotelWebhook(BaseModel):
    eventID: str | None = None
    eventId: str | None = None
    notificationID: int | None = None
    hotelCode: str | None = None
    notificationType: str | None = None
    payload: WebhookPayload | None = None


@router.post("/minihotel")
async def minihotel_webhook(
    body: MiniHotelWebhook,
    db: AsyncSession = Depends(get_db),
):
    if not body.payload or not body.payload.reservationNumber:
        return {"status": "ignored", "reason": "no reservationNumber"}

    payload = body.payload
    res_number = payload.reservationNumber
    mh_status = (payload.status or "").upper()

    # Guest info from first room or payload root
    first_room = payload.rooms[0] if payload.rooms else None
    guest_name = ""
    room_name = ""
    guest_phone = payload.guestPhone or ""

    if first_room:
        parts = [first_room.guestFirstName or "", first_room.guestLastName or ""]
        guest_name = " ".join(p for p in parts if p).strip()
        room_name = _normalise_room(first_room.roomNumber or "")
        if not guest_phone:
            guest_phone = first_room.guestPhone or ""

    # Parse dates
    check_in = _parse_date(payload.checkIn or (first_room.checkIn if first_room else None))
    check_out = _parse_date(payload.checkOut or (first_room.checkOut if first_room else None))

    # Upsert booking
    result = await db.execute(
        select(Booking).where(Booking.minihotel_id == res_number)
    )
    booking = result.scalar_one_or_none()
    is_brand_new = booking is None

    if is_brand_new:
        booking = Booking(
            minihotel_id=res_number,
            guest_name=guest_name or f"Guest {res_number}",
            guest_phone=guest_phone,
            room_name=room_name,
            check_in=check_in or datetime.utcnow().date(),
            check_out=check_out or datetime.utcnow().date(),
            total_price=payload.totalPrice or 0,
            status=_map_status(mh_status),
            source="minihotel",
            synced_at=datetime.utcnow(),
        )
        db.add(booking)
        await db.flush()
    else:
        if guest_name:
            booking.guest_name = guest_name
        if room_name:
            booking.room_name = room_name
        if guest_phone and not booking.guest_phone:
            booking.guest_phone = guest_phone
        if check_in:
            booking.check_in = check_in
        if check_out:
            booking.check_out = check_out
        if payload.totalPrice:
            booking.total_price = payload.totalPrice
        booking.status = _map_status(mh_status)
        booking.synced_at = datetime.utcnow()

    await db.commit()
    await db.refresh(booking)

    # הזמנה חדשה: שלח אישור מיד + תזמן שאר ההודעות
    if is_brand_new and booking.guest_phone:
        await trigger_confirmation(booking, db)
        schedule_booking_messages(booking)

    return {
        "status": "ok",
        "booking_id": booking.id,
        "minihotel_id": res_number,
        "is_new": is_brand_new,
        "guest_name": booking.guest_name,
        "room": booking.room_name,
        "booking_status": booking.status,
        "messages_scheduled": is_brand_new and bool(booking.guest_phone),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_status(mh_status: str) -> str:
    mapping = {
        "IN": "checked_in",
        "OK": "confirmed",
        "CONFIRMED": "confirmed",
        "CANCELLED": "cancelled",
        "CANCEL": "cancelled",
        "NO-SHOW": "no_show",
    }
    return mapping.get(mh_status.upper(), "confirmed")


def _normalise_room(room_number: str) -> str:
    mapping = {
        "0101": "Sea",
        "0102": "Sesert",
        "1": "Sea",
        "2": "Sesert",
    }
    return mapping.get(room_number, room_number or "")


def _parse_date(val: str | None):
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None
