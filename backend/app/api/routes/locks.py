import time
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.ttlock import ttlock_client
from app.models import Booking

router = APIRouter()

# Map room names to TTLock lock IDs — populate after TTLock setup
ROOM_LOCK_MAP: dict[str, int] = {
    # "חדר מדבר": 123456,
    # "חדר ים": 654321,
}


@router.get("/")
async def list_locks():
    return await ttlock_client.list_locks()


@router.post("/bookings/{booking_id}/generate-code")
async def generate_entry_code(booking_id: int, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")

    lock_id = ROOM_LOCK_MAP.get(booking.room_name)
    if not lock_id:
        raise HTTPException(status_code=400, detail=f"מנעול לא מוגדר לחדר: {booking.room_name}")

    start_ms = int(datetime.combine(booking.check_in, datetime.min.time()).timestamp() * 1000)
    end_ms = int(datetime.combine(booking.check_out, datetime.min.time()).timestamp() * 1000)

    result = await ttlock_client.generate_passcode(
        lock_id=lock_id,
        passcode_name=f"Guest-{booking.id}-{booking.guest_name}",
        start_date=start_ms,
        end_date=end_ms,
    )

    booking.entry_code = result.get("keyboardPwd")
    await db.commit()
    return {"code": booking.entry_code, "lock_id": lock_id}
