"""
MiniHotel Webhook handler.

Handles the generic MiniHotel webhook envelope:
  { eventID, notificationID, hotelCode, notificationType, payload }

Supported notificationType values:
  - reservation.created / reservation.updated / reservation.cancelled
        → real booking data (guest, dates, phone, price). This is what
          drives new-booking automation (WhatsApp messages, TTLock codes).
  - room.occupancy.updated
        → today-only occupied/vacated signal. Used opportunistically to
          fill in missing details on an EXISTING booking; never creates
          a new booking by itself (per MiniHotel docs, it only reflects
          today's state, not full reservation context).

Authentication: HTTP Basic Auth (required by MiniHotel's webhook spec).
Credentials are configured via settings.minihotel_webhook_user /
settings.minihotel_webhook_password and given to MiniHotel out-of-band.
"""
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Booking
from app.scheduler import trigger_confirmation, schedule_booking_messages, cancel_scheduled_jobs

router = APIRouter()
security = HTTPBasic()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_webhook_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate Basic Auth against configured MiniHotel webhook credentials.
    Uses secrets.compare_digest to avoid timing attacks.
    """
    valid_user = secrets.compare_digest(credentials.username, settings.minihotel_webhook_user)
    valid_pass = secrets.compare_digest(credentials.password, settings.minihotel_webhook_password)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# ---------------------------------------------------------------------------
# Generic envelope — payload is parsed manually per notificationType,
# since reservation.* and room.occupancy.updated have different shapes.
# ---------------------------------------------------------------------------

class MiniHotelWebhook(BaseModel):
    eventID: str | None = None
    eventId: str | None = None  # docs warn: capital-D vs lowercase-d varies
    notificationID: int | None = None
    hotelCode: str | None = None
    notificationType: str | None = None
    payload: dict = {}


@router.post("/minihotel")
async def minihotel_webhook(
    body: MiniHotelWebhook,
    db: AsyncSession = Depends(get_db),
    _auth: bool = Depends(verify_webhook_auth),
):
    ntype = body.notificationType or ""

    if ntype.startswith("reservation."):
        return await _handle_reservation_event(body, db)
    elif ntype == "room.occupancy.updated":
        return await _handle_occupancy_event(body, db)
    else:
        return {"status": "ignored", "reason": f"unhandled notificationType: {ntype!r}"}


# ---------------------------------------------------------------------------
# reservation.created / reservation.updated / reservation.cancelled
# ---------------------------------------------------------------------------

async def _handle_reservation_event(body: MiniHotelWebhook, db: AsyncSession):
    payload = body.payload or {}
    res_number = payload.get("reservationNumber")
    if not res_number:
        return {"status": "ignored", "reason": "no reservationNumber"}

    mh_status = (payload.get("status") or "").upper()
    header = payload.get("header") or {}
    total = payload.get("total") or {}

    guest_first = header.get("firstName", "")
    guest_last = header.get("lastName", "")
    guest_name = " ".join(p for p in [guest_first, guest_last] if p).strip()
    guest_phone = header.get("phone") or ""
    guest_email = header.get("email") or None

    # header.rooms is an array; our schema stores ONE room per booking.
    # CONFIRMED (booking 460, 8.7.26): a reservation spanning both cabins
    # doesn't arrive as two array entries — MiniHotel sends it as a single
    # room whose raw roomNumber/roomType is literally "Des_Sea" (this is
    # the dedicated 3rd MiniHotel listing used for Airbnb bookings of both
    # cabins together, since Airbnb can't offer 2 separate units as one
    # listing). So taking first_room is correct; the actual multi-lock
    # complexity lives downstream in ttlock.py (_resolve_lock_ids), not here.
    header_rooms = header.get("rooms") or []
    first_room = header_rooms[0] if header_rooms else {}
    room_name = _normalise_room(first_room.get("roomNumber"), first_room.get("roomType"))

    check_in = _parse_date(header.get("checkInDate"))
    check_out = _parse_date(header.get("checkOutDate"))

    total_price = total.get("amount")
    if total_price is None:
        total_price = total.get("amountAfterTaxes")

    result = await db.execute(select(Booking).where(Booking.minihotel_id == res_number))
    booking = result.scalar_one_or_none()
    is_brand_new = booking is None

    if is_brand_new:
        booking = Booking(
            minihotel_id=res_number,
            guest_name=guest_name or f"Guest {res_number}",
            guest_phone=guest_phone,
            guest_email=guest_email,
            room_name=room_name,
            check_in=check_in or datetime.utcnow().date(),
            check_out=check_out or datetime.utcnow().date(),
            total_price=total_price or 0,
            status=_map_status(mh_status),
            source=payload.get("source") or "minihotel",
            synced_at=datetime.utcnow(),
        )
        db.add(booking)
        await db.flush()
    else:
        if guest_name:
            booking.guest_name = guest_name
        if room_name:
            booking.room_name = room_name
        if guest_phone:
            booking.guest_phone = guest_phone
        if guest_email:
            booking.guest_email = guest_email
        if check_in:
            booking.check_in = check_in
        if check_out:
            booking.check_out = check_out
        if total_price is not None:
            booking.total_price = total_price
        booking.status = _map_status(mh_status)
        booking.synced_at = datetime.utcnow()

    await db.commit()
    await db.refresh(booking)

    # הזמנה בוטלה — מבטלים כל job מתוזמן שנרשם לה קודם (pre_arrival,
    # entry_code, checkout). לא סומכים רק על זה (ה-job היה נמחק ממילא
    # בדיפלוי הבא כי אין persistence — לכן יש גם הגנה בזמן-ריצה ב-
    # assign_passcode_to_booking), אבל זה מונע שליחה מיותרת אם אין
    # דיפלוי בין הביטול לבין מועד ה-job.
    if mh_status == "CL":
        cancel_scheduled_jobs(booking.id)

    # New confirmed booking with a phone number → send confirmation now,
    # schedule the rest of the automated messages.
    #
    # IMPORTANT: this must never raise. The booking is already committed
    # above — a downstream failure here (e.g. Twilio rejecting a bad
    # number) must not turn into a 500, or MiniHotel will retry the same
    # event up to 6 times over 6 hours (per their retry policy) for a
    # problem that re-sending the webhook can't fix.
    should_notify = (
        is_brand_new
        and booking.guest_phone
        and mh_status != "CL"
    )
    notify_error = None
    if should_notify:
        try:
            await trigger_confirmation(booking, db)
            schedule_booking_messages(booking)
        except Exception as exc:  # noqa: BLE001 — deliberately broad, see comment above
            notify_error = str(exc)

    return {
        "status": "ok",
        "notificationType": body.notificationType,
        "booking_id": booking.id,
        "minihotel_id": res_number,
        "is_new": is_brand_new,
        "guest_name": booking.guest_name,
        "room": booking.room_name,
        "booking_status": booking.status,
        "messages_scheduled": should_notify and notify_error is None,
        "notify_error": notify_error,
        # visible for calibrating _normalise_room against real MiniHotel data
        "raw_room": {"roomNumber": first_room.get("roomNumber"), "roomType": first_room.get("roomType")},
    }


# ---------------------------------------------------------------------------
# room.occupancy.updated — today-only signal, enrich existing bookings only
# ---------------------------------------------------------------------------

async def _handle_occupancy_event(body: MiniHotelWebhook, db: AsyncSession):
    payload = body.payload or {}
    res_number = payload.get("reservationNumber")
    if not res_number:
        return {"status": "ignored", "reason": "no reservationNumber"}

    rooms = payload.get("rooms") or []
    first_room = rooms[0] if rooms else {}

    result = await db.execute(select(Booking).where(Booking.minihotel_id == res_number))
    booking = result.scalar_one_or_none()
    if booking is None:
        return {
            "status": "ignored",
            "reason": "occupancy event for unknown reservation (waiting for reservation.created)",
            "minihotel_id": res_number,
        }

    # Only fill in gaps — never overwrite data we already trust from
    # reservation.* events, since occupancy payloads are today-scoped.
    if not booking.guest_phone and first_room.get("phone"):
        booking.guest_phone = first_room["phone"]
    if not booking.guest_email and first_room.get("email"):
        booking.guest_email = first_room["email"]

    booking.synced_at = datetime.utcnow()
    await db.commit()

    return {
        "status": "ok",
        "notificationType": "room.occupancy.updated",
        "booking_id": booking.id,
        "occupied": first_room.get("occupied"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_status(mh_status: str) -> str:
    mapping = {
        "OK": "confirmed",
        "IN": "checked_in",
        "OUT": "checked_out",
        "CL": "cancelled",
    }
    return mapping.get(mh_status.upper(), "confirmed")


def _normalise_room(room_number: str | None, room_type: str | None = None) -> str:
    """Map MiniHotel's roomNumber/roomType to our internal desert/sea naming.

    CONFIRMED against real MiniHotel events (8.7.26, via Yuval's test
    booking 460): the "0101"/"0102"/"1"/"2" entries below are still
    unconfirmed guesses (kept as-is until we see one fire for real), but
    the fallback path IS confirmed correct — MiniHotel's combined-cabin
    listing sends its raw value as literally "Des_Sea", which falls
    through to the `return room_number or room_type` line below and is
    then picked up by ttlock.py's _resolve_lock_ids() as the dual-lock case.
    """
    mapping = {
        "0101": "Sea",
        "0102": "Desert",
        "1": "Sea",
        "2": "Desert",
    }
    for candidate in (room_number, room_type):
        if candidate and candidate in mapping:
            return mapping[candidate]
    # Fallback: surface the raw value instead of silently returning "" —
    # better to see something unmapped than nothing at all.
    return room_number or room_type or ""


def _parse_date(val: str | None):
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None
