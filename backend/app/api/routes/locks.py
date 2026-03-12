from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.ttlock import (
    assign_passcode_to_booking,
    remove_passcode_after_checkout,
    list_passcodes,
    get_lock_status,
    LOCK_IDS,
)
from app.models import Booking

router = APIRouter()


@router.get("/status")
async def locks_status():
    """סטטוס שני המנעולים — סוללה, חיבור."""
    results = {}
    for room, lock_id in LOCK_IDS.items():
        try:
            data = await get_lock_status(lock_id)
            results[room] = {
                "lockId":          lock_id,
                "electricQuantity": data.get("electricQuantity"),
                "lockName":        data.get("lockName"),
                "online":          data.get("hasGateway") == 1,
            }
        except Exception as e:
            results[room] = {"lockId": lock_id, "error": str(e)}
    return results


@router.get("/{room}/passcodes")
async def list_room_passcodes(room: str):
    """רשימת קודים פעילים לחדר (desert / sea)."""
    lock_id = LOCK_IDS.get(room)
    if not lock_id:
        raise HTTPException(status_code=404, detail=f"חדר לא מוכר: {room}")
    return await list_passcodes(lock_id)


@router.post("/bookings/{booking_id}/assign-code")
async def assign_code(
    booking_id: int,
    passcode: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """יצירת קוד כניסה להזמנה ושמירתו ב-DB."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")
    if not booking.check_in or not booking.check_out:
        raise HTTPException(status_code=400, detail="חסרות תאריכי כניסה/יציאה")

    code = await assign_passcode_to_booking(booking, db, passcode)
    return {
        "booking_id": booking_id,
        "entry_code": code,
        "guest_name": booking.guest_name,
        "room":       booking.room_name,
    }


@router.delete("/bookings/{booking_id}/remove-code")
async def remove_code(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
):
    """מחיקת קוד כניסה אחרי יציאה."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")

    ok = await remove_passcode_after_checkout(booking, db)
    return {"booking_id": booking_id, "deleted": ok}
