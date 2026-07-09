from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.booking import Booking
from app.models.checkin_token import CheckinToken

router = APIRouter(prefix="/public", tags=["public-checkin"])


@router.get("/entry-code/{token}")
async def get_entry_code(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CheckinToken).where(CheckinToken.token == token))
    checkin_token = result.scalar_one_or_none()

    if not checkin_token:
        raise HTTPException(status_code=404, detail="קישור לא תקין")

    if checkin_token.expires_at < date.today():
        raise HTTPException(status_code=410, detail="הקישור פג תוקף — פנו אלינו")

    booking = await db.get(Booking, checkin_token.booking_id)
    if not booking or not booking.entry_code:
        raise HTTPException(status_code=404, detail="הקוד עדיין לא נוצר, נסו שוב מאוחר יותר")

    return {
        "guest_name": booking.guest_name,
        "room_name": booking.room_name,
        "entry_code": booking.entry_code,
        "checkin_date": booking.check_in.isoformat(),
        "checkout_date": booking.check_out.isoformat(),
        "checkin_time": getattr(booking, "checkin_time", "15:00"),
        "checkout_time": getattr(booking, "checkout_time", "11:00"),
    }
