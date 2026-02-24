from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.minihotel import minihotel_client
from app.models import Booking

router = APIRouter()


@router.get("/")
async def list_bookings(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Booking).order_by(Booking.check_in)
    if from_date:
        query = query.where(Booking.check_in >= from_date)
    if to_date:
        query = query.where(Booking.check_out <= to_date)
    result = await db.scalars(query)
    return result.all()


@router.post("/sync")
async def sync_bookings(
    from_date: date,
    to_date: date,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a sync from MiniHotel."""
    raw = await minihotel_client.get_bookings(str(from_date), str(to_date))
    return {"synced": len(raw)}


@router.get("/stats/occupancy")
async def occupancy_stats(month: str):
    """Get occupancy stats for a month (YYYY-MM)."""
    return await minihotel_client.get_occupancy_stats(month)


@router.get("/{booking_id}")
async def get_booking(booking_id: int, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")
    return booking
