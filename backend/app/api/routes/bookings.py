from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, extract
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
    synced = 0
    for item in raw:
        existing = await db.scalar(
            select(Booking).where(Booking.minihotel_id == str(item["id"]))
        )
        if existing:
            existing.check_in = item.get("check_in", existing.check_in)
            existing.check_out = item.get("check_out", existing.check_out)
            existing.status = item.get("status", existing.status)
            existing.total_price = item.get("total_price", existing.total_price)
            existing.room_name = item.get("room_name", existing.room_name)
        else:
            new_booking = Booking(
                minihotel_id=str(item["id"]),
                guest_name=item.get("guest_name", ""),
                guest_phone=item.get("guest_phone", ""),
                room_name=item.get("room_name", ""),
                check_in=item.get("check_in"),
                check_out=item.get("check_out"),
                total_price=item.get("total_price", 0),
                status=item.get("status", "confirmed"),
            )
            db.add(new_booking)
        synced += 1
    await db.commit()
    return {"synced": synced}

@router.get("/stats/occupancy")
async def occupancy_stats(month: str, db: AsyncSession = Depends(get_db)):
    """Get occupancy stats for a month (YYYY-MM format), calculated locally."""
    import calendar
    
    year, mon = int(month.split("-")[0]), int(month.split("-")[1])
    days_in_month = calendar.monthrange(year, mon)[1]
    
    query = select(Booking).where(
        extract("year", Booking.check_in) == year,
        extract("month", Booking.check_in) == mon,
        Booking.status == "confirmed"
    )
    result = await db.scalars(query)
    bookings = result.all()
    
    desert_nights = 0
    sea_nights = 0
    
    for b in bookings:
        nights = (b.check_out - b.check_in).days
        room = (b.room_name or "").strip()
        
        if room == "des_sea":
            desert_nights += nights
            sea_nights += nights
        elif room == "sesert":
            desert_nights += nights
        elif room == "sea":
            sea_nights += nights
    
    return {
        "month": month,
        "days_in_month": days_in_month,
        "desert": {
            "nights_booked": desert_nights,
            "occupancy_pct": round(desert_nights / days_in_month * 100, 1)
        },
        "sea": {
            "nights_booked": sea_nights,
            "occupancy_pct": round(sea_nights / days_in_month * 100, 1)
        },
        "combined": {
            "nights_booked": desert_nights + sea_nights,
            "occupancy_pct": round((desert_nights + sea_nights) / (days_in_month * 2) * 100, 1)
        }
    }


@router.get("/{booking_id}")
async def get_booking(booking_id: int, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")
    return booking
