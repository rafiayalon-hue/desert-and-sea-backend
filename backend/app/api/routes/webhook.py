"""
MiniHotel Webhook handler.
Receives room.occupancy.updated events from MiniHotel and upserts bookings into DB.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking, MessageLog
from app.scheduler import trigger_confirmation

router = APIRouter()


class WebhookRoom(BaseModel):
    roomNumber: str | None = None
    guestFirstName: str | None = None
    guestLastName: str | None = None
    occupied: bool = False


class WebhookPayload(BaseModel):
    reservationNumber: str | None = None
    status: str | None = None
    rooms: list[WebhookRoom] = []
    timestamp: str | None = None


class MiniHotelWebhook(BaseModel):
    eventID: str | None = None
    eventId: str | None = None  # MiniHotel uses both spellings
    notificationID: int | None = None
    hotelCode: str | None = None
    notificationType: str | None = None
    payload: WebhookPayload | None = None


@router.post("/minihotel")
async def minihotel_webhook(
    body: MiniHotelWebhook,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive MiniHotel webhook events.
    Handles: room.occupancy.updated
    """
    if not body.payload or not body.payload.reservationNumber:
        return {"status": "ignored", "reason": "no reservationNumber"}

    payload = body.payload
    res_number = payload.reservationNumber
    mh_status = (payload.status or "").upper()

    # Build guest name from first room
    first_room = payload.rooms[0] if payload.rooms else None
    guest_name = ""
    room_name = ""
    if first_room:
        parts = [first_room.guestFirstName or "", first_room.guestLastName or ""]
        guest_name = " ".join(p for p in parts if p).strip()
        room_name = first_room.roomNumber or ""

    # Normalise room name (0101 → Sea, 0102 → Sesert, etc.)
    room_display = _normalise_room(room_name)

    # Normalise status
    is_new = mh_status in ("OK", "CONFIRMED", "")
    is_checkin = mh_status == "IN"
    is_checkout = not first_room.occupied if first_room else False

    # --- Upsert booking ---
    result = await db.execute(
        select(Booking).where(Booking.minihotel_id == res_number)
    )
    booking = result.scalar_one_or_none()

    if booking is None:
        # New booking — create with minimal data
        booking = Booking(
            minihotel_id=res_number,
            guest_name=guest_name or f"Guest {res_number}",
            room_name=room_display,
            check_in=datetime.utcnow().date(),   # placeholder — update manually
            check_out=datetime.utcnow().date(),  # placeholder
            total_price=0,
            status=_map_status(mh_status),
            source="minihotel",
            synced_at=datetime.utcnow(),
        )
        db.add(booking)
        await db.flush()  # get booking.id
        is_brand_new = True
    else:
        # Update existing
        if guest_name:
            booking.guest_name = guest_name
        if room_display:
            booking.room_name = room_display
        booking.status = _map_status(mh_status)
        booking.synced_at = datetime.utcnow()
        is_brand_new = False

    await db.commit()
    await db.refresh(booking)

    # --- Trigger confirmation message for brand-new bookings ---
    if is_brand_new and booking.guest_phone:
        await trigger_confirmation(booking, db)

    return {
        "status": "ok",
        "booking_id": booking.id,
        "minihotel_id": res_number,
        "is_new": is_brand_new,
        "guest_name": booking.guest_name,
        "room": booking.room_name,
        "booking_status": booking.status,
    }


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
    """Map MiniHotel room numbers to display names."""
    mapping = {
        "0101": "Sea",
        "0102": "Sesert",
        "1": "Sea",
        "2": "Sesert",
    }
    return mapping.get(room_number, room_number or "")
