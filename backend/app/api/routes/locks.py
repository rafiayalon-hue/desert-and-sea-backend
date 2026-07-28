from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.integrations.ttlock import (
    assign_passcode_to_booking,
    remove_passcode_after_checkout,
    list_passcodes,
    delete_passcode_by_id,  # NEW (28.7.26)
    get_lock_status,
    LOCK_IDS,
)
from app.scheduler import send_entry_code_now
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


# NEW (28.7.26): "ניהול מנעולים" — משווה בין כל הקודים שקיימים בפועל
# בשני המנעולים (TTLock) לבין הזמנות פעילות ב-DB, ומסמן קוד כ"יתום" אם
# הוא לא מוכר לאף הזמנה פעילה (למשל checkout cleanup שנכשל בשקט, או
# קוד ישן שנשאר מסיבה אחרת). זה מה שהעמוד "ניהול מנעולים" בדשבורד קורא.
@router.get("/audit")
async def audit_passcodes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Booking).where(Booking.ttlock_pwd_ids.isnot(None)))
    bookings = result.scalars().all()

    # מפה מ-"lockId:keyboardPwdId" → ההזמנה הפעילה שהקוד הזה שייך לה.
    # הזמנות מבוטלות לא נחשבות "לגיטימיות" — קוד ששייך רק להן ייחשב יתום.
    legitimate: dict[str, Booking] = {}
    for b in bookings:
        if (b.status or "").strip().lower() == "cancelled":
            continue
        for entry in (b.ttlock_pwd_ids or "").split(","):
            entry = entry.strip()
            if entry:
                legitimate[entry] = b

    audit = {}
    for room, lock_id in LOCK_IDS.items():
        try:
            passcodes = await list_passcodes(lock_id)
        except Exception as e:
            audit[room] = {"error": str(e)}
            continue

        rows = []
        for p in passcodes:
            pwd_id = p.get("keyboardPwdId")
            key = f"{lock_id}:{pwd_id}"
            booking = legitimate.get(key)
            rows.append({
                "keyboardPwdId": pwd_id,
                "name": p.get("keyboardPwdName"),
                "passcode": p.get("keyboardPwd"),
                "startDate": p.get("startDate"),
                "endDate": p.get("endDate"),
                "is_orphan": booking is None,
                "booking_id": booking.id if booking else None,
                "guest_name": booking.guest_name if booking else None,
                "check_in": booking.check_in.isoformat() if booking and booking.check_in else None,
                "check_out": booking.check_out.isoformat() if booking and booking.check_out else None,
            })
        audit[room] = rows
    return audit


@router.delete("/{room}/passcodes/{keyboard_pwd_id}")
async def delete_room_passcode(room: str, keyboard_pwd_id: int):
    """
    NEW (28.7.26): מחיקה ישירה של קוד מהמנעול — לניקוי קודים יתומים
    שהתגלו ב-audit. לא קשור בהכרח להזמנה ספציפית ב-DB (בניגוד ל-
    remove-code למטה, שמנקה גם את השדות ב-booking).
    """
    lock_id = LOCK_IDS.get(room)
    if not lock_id:
        raise HTTPException(status_code=404, detail=f"חדר לא מוכר: {room}")
    await delete_passcode_by_id(lock_id, keyboard_pwd_id)
    return {"deleted": True, "room": room, "keyboardPwdId": keyboard_pwd_id}


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
    # שולח את הודעת קוד-הכניסה עכשיו (אידמפוטנטי — אם כבר נשלחה לא ישלח
    # שוב), ומבטל את ה-fallback האוטומטי כדי שלא ירוץ שוב על הזמנה הזו.
    if booking.guest_phone:
        await send_entry_code_now(booking, db)
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
