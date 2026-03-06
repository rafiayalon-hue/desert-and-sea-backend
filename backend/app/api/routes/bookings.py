from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.integrations.minihotel import minihotel_client
from app.models import Booking
import calendar

router = APIRouter()

ACTIVE_STATUSES = {"confirmed", "channel manager", "homepage"}


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
    year, mon = int(month.split("-")[0]), int(month.split("-")[1])
    days_in_month = calendar.monthrange(year, mon)[1]
    month_start = date(year, mon, 1)
    month_end = date(year, mon, days_in_month)

    query = select(Booking).where(
        and_(
            Booking.check_in < month_end + timedelta(days=1),
            Booking.check_out > month_start,
        )
    )
    result = await db.scalars(query)
    bookings = result.all()

    desert_nights = 0
    sea_nights = 0

    for b in bookings:
        status = (b.status or "").strip().lower()
        if status not in ACTIVE_STATUSES:
            continue

        start = max(b.check_in, month_start)
        end = min(b.check_out, month_end + timedelta(days=1))
        nights = (end - start).days
        if nights <= 0:
            continue

        room = (b.room_name or "").strip().lower().replace(" ", "")

        if "des_sea" in room:
            desert_nights += nights
            sea_nights += nights
        elif "sea" in room and "sesert" in room:
            desert_nights += nights
            sea_nights += nights
        elif "sesert" in room:
            desert_nights += nights
        elif "sea" in room:
            sea_nights += nights

    return {
        "month": month,
        "days_in_month": days_in_month,
        "desert": {
            "nights_booked": desert_nights,
            "occupancy_pct": round(desert_nights / days_in_month * 100, 1),
        },
        "sea": {
            "nights_booked": sea_nights,
            "occupancy_pct": round(sea_nights / days_in_month * 100, 1),
        },
        "combined": {
            "nights_booked": desert_nights + sea_nights,
            "occupancy_pct": round(
                (desert_nights + sea_nights) / (days_in_month * 2) * 100, 1
            ),
        },
    }


@router.get("/{booking_id}")
async def get_booking(booking_id: int, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")
    return booking
@router.post("/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload historical bookings from MiniHotel Excel export."""
    import io
    from datetime import datetime
    import openpyxl

    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents))
    ws = wb.active

    inserted = 0
    updated = 0
    errors = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        minihotel_id = str(row[0]) if row[0] else None
        if not minihotel_id:
            continue
        try:
            first_name = row[1] or ""
            last_name = row[2] or ""
            guest_name = f"{first_name} {last_name}".strip()
            check_in = row[3].date() if isinstance(row[3], datetime) else row[3]
            check_out = row[4].date() if isinstance(row[4], datetime) else row[4]
            nights = row[5] or 0
            source = row[7] or ""
            email = row[10] or ""
            status = row[13] or ""
            total_price_str = str(row[15] or "0").replace("ILS ", "").replace(",", "").strip()
            try:
                total_price = float(total_price_str)
            except Exception:
                total_price = 0.0
            notes = row[17] or ""
            room_name = row[18] or ""

            existing = await db.scalar(
                select(Booking).where(Booking.minihotel_id == minihotel_id)
            )
            if existing:
                existing.guest_name = guest_name
                existing.check_in = check_in
                existing.check_out = check_out
                existing.status = status
                existing.total_price = total_price
                existing.room_name = room_name
                existing.notes = notes
                updated += 1
            else:
                new_booking = Booking(
                    minihotel_id=minihotel_id,
                    guest_name=guest_name,
                    guest_phone="",
                    guest_email=email,
                    room_name=room_name,
                    check_in=check_in,
                    check_out=check_out,
                    nights=nights,
                    total_price=total_price,
                    status=status,
                    source=source,
                    notes=notes,
                )
                db.add(new_booking)
                inserted += 1
        except Exception as e:
            errors += 1
            continue

    await db.commit()
    return {"inserted": inserted, "updated": updated, "errors": errors}
