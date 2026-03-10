from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
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
    raw = await minihotel_client.get_bookings(str(from_date), str(to_date))
    synced = 0
    for item in raw:
        existing = await db.scalar(
            select(Booking).where(Booking.minihotel_id == str(item["id"]))
        )
        if existing:
            existing.check_in    = item.get("check_in",    existing.check_in)
            existing.check_out   = item.get("check_out",   existing.check_out)
            existing.status      = item.get("status",      existing.status)
            existing.total_price = item.get("total_price", existing.total_price)
            existing.room_name   = item.get("room_name",   existing.room_name)
            existing.guest_phone = item.get("guest_phone", existing.guest_phone)
            existing.source      = item.get("source",      existing.source)
        else:
            new_booking = Booking(
                minihotel_id=str(item["id"]),
                guest_name=item.get("guest_name", ""),
                guest_phone=item.get("guest_phone", ""),
                guest_email=item.get("guest_email"),
                country=item.get("country"),
                adults=item.get("adults", 1),
                children=item.get("children", 0),
                room_name=item.get("room_name", ""),
                check_in=item.get("check_in"),
                check_out=item.get("check_out"),
                total_price=item.get("total_price", 0),
                balance=item.get("balance", 0),
                status=item.get("status", "confirmed"),
                source=item.get("source"),
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


def parse_price(val) -> float:
    try:
        return float(str(val or "0").replace("ILS ", "").replace(",", "").strip())
    except Exception:
        return 0.0


def parse_source(portal_val) -> str:
    if not portal_val or str(portal_val).strip().lower() in ("nan", ""):
        return "direct"
    v = str(portal_val).strip().upper()
    if v == "AIRBNB":
        return "airbnb"
    if v == "BOENGINE":
        return "website"
    return "direct"


@router.post("/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
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
            first_name  = row[1] or ""
            last_name   = row[2] or ""
            guest_name  = f"{first_name} {last_name}".strip()
            check_in    = row[3].date() if isinstance(row[3], datetime) else row[3]
            check_out   = row[4].date() if isinstance(row[4], datetime) else row[4]
            portal      = row[8]
            country     = str(row[9]) if row[9] else None
            guest_email = str(row[10]) if row[10] else None
            adults      = int(row[11]) if row[11] else 1
            children    = int(row[12]) if row[12] else 0
            status      = row[13] or ""
            total_price = parse_price(row[15])
            notes       = str(row[17]) if row[17] else None
            room_name   = row[18] or ""
            balance     = parse_price(row[19])
            source      = parse_source(portal)

            existing = await db.scalar(
                select(Booking).where(Booking.minihotel_id == minihotel_id)
            )
            if existing:
                existing.guest_name  = guest_name
                existing.guest_email = guest_email
                existing.country     = country
                existing.adults      = adults
                existing.children    = children
                existing.check_in    = check_in
                existing.check_out   = check_out
                existing.status      = status
                existing.total_price = total_price
                existing.balance     = balance
                existing.room_name   = room_name
                existing.source      = source
                existing.notes       = notes
                updated += 1
            else:
                new_booking = Booking(
                    minihotel_id=minihotel_id,
                    guest_name=guest_name,
                    guest_phone="",
                    guest_email=guest_email,
                    country=country,
                    adults=adults,
                    children=children,
                    room_name=room_name,
                    check_in=check_in,
                    check_out=check_out,
                    total_price=total_price,
                    balance=balance,
                    status=status,
                    source=source,
                    notes=notes,
                )
                db.add(new_booking)
                inserted += 1
        except Exception:
            errors += 1
            continue

    await db.commit()
    return {"inserted": inserted, "updated": updated, "errors": errors}


from pydantic import BaseModel
from typing import Optional


class BookingUpdate(BaseModel):
    notes: Optional[str] = None
    payment_method: Optional[str] = None
    payment_link: Optional[str] = None
    guest_phone: Optional[str] = None
    checkin_time: Optional[str] = None
    checkout_time: Optional[str] = None
    guest_name: Optional[str] = None


@router.patch("/{booking_id}")
async def update_booking(
    booking_id: int,
    data: BookingUpdate,
    db: AsyncSession = Depends(get_db),
):
    from app.scheduler import schedule_booking_messages, trigger_confirmation

    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")

    had_phone = bool(booking.guest_phone)

    if data.notes is not None:
        booking.notes = data.notes
    if data.payment_method is not None:
        booking.payment_method = data.payment_method
    if data.payment_link is not None:
        booking.payment_link = data.payment_link
    if data.checkin_time is not None:
        booking.checkin_time = data.checkin_time
    if data.checkout_time is not None:
        booking.checkout_time = data.checkout_time
    if data.guest_name is not None:
    booking.guest_name = data.guest_name.strip()
  

    is_returning = False

    if data.guest_phone is not None:
        new_phone = data.guest_phone.strip()
        booking.guest_phone = new_phone

        # ── זיהוי אורח חוזר לפי טלפון ──────────────────────────────
        if new_phone:
            from sqlalchemy import select as sa_select

            def _norm(p: str) -> str:
                p = p.strip().replace("-", "").replace(" ", "")
                if p.startswith("+972"):
                    p = "0" + p[4:]
                elif p.startswith("972"):
                    p = "0" + p[3:]
                return p

            norm_new = _norm(new_phone)

            existing = await db.scalars(
                sa_select(Booking).where(
                    Booking.id != booking_id,
                    Booking.guest_phone != "",
                    Booking.guest_phone.isnot(None),
                )
            )
            other_bookings = existing.all()

            matches = [b for b in other_bookings if _norm(b.guest_phone or "") == norm_new]
            active_matches = [
                b for b in matches
                if (b.status or "").lower() not in ("cancelled", "cancel")
            ]

            if active_matches:
                is_returning = True
                names = {b.guest_name for b in active_matches}
                if len(names) > 1:
                    import logging
                    logging.warning(
                        f"[GUEST_LOOKUP] Phone {new_phone} found under multiple names: {names}"
                    )

    await db.commit()
    await db.refresh(booking)

    # ── הפעל תזמון WhatsApp אם נוסף טלפון לראשונה ──
    phone_just_added = (not had_phone) and bool(booking.guest_phone)
    if phone_just_added:
        await trigger_confirmation(booking, db)
        schedule_booking_messages(booking)

    return {
        **booking.__dict__,
        "automation_triggered": phone_just_added,
        "is_returning_guest": is_returning,
    }
