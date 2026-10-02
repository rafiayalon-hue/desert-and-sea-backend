"""
NEW (30.9.26) — כלים לתקופה ש-WhatsApp (Twilio) לא זמין.

GET  /api/fallback/backfill?days=14            → רשימה בלבד (לא שולח)
POST /api/fallback/backfill?days=14            → שולח אישורי הזמנה חסרים
GET  /api/fallback/wa-link/{booking_id}/{type} → טקסט + קישור wa.me לכפתור "שלח בוואטסאפ"
GET  /api/fallback/sms-test?phone=05...        → SMS בדיקה (לוודא ש-019 מחובר)

כל הנתיבים דורשים header:  X-HA-Token: <HA_TOKEN>  (אותו טוקן של HA).
type: confirmation / pre_arrival / entry_code / checkout
"""
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.sms import SmsError, send_sms
from app.models import Booking
from app.scheduler import backfill_missing_confirmations, build_sms_text

router = APIRouter(prefix="/api/fallback", tags=["fallback"])

TYPES = {"confirmation", "pre_arrival", "entry_code", "checkout"}


def _auth(x_ha_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("HA_TOKEN")
    if not expected or x_ha_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _wa_number(phone: str) -> str:
    p = "".join(ch for ch in (phone or "") if ch.isdigit())
    if p.startswith("0"):
        p = "972" + p[1:]
    return p


@router.get("/backfill", dependencies=[Depends(_auth)])
async def backfill_preview(days: int = 14):
    rows = await backfill_missing_confirmations(days=days, dry_run=True)
    return {"dry_run": True, "count": len(rows), "bookings": rows}


@router.post("/backfill", dependencies=[Depends(_auth)])
async def backfill_send(days: int = 14):
    rows = await backfill_missing_confirmations(days=days, dry_run=False)
    return {"dry_run": False, "count": len(rows), "bookings": rows}


@router.get("/wa-link/{booking_id}/{message_type}", dependencies=[Depends(_auth)])
async def wa_link(booking_id: int, message_type: str, db: AsyncSession = Depends(get_db)):
    if message_type not in TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(TYPES)}")
    booking = await db.get(Booking, booking_id)
    if booking is None or not booking.guest_phone:
        raise HTTPException(status_code=404, detail="booking or phone not found")
    text = await build_sms_text(message_type, booking, db)
    await db.commit()  # אם נוצר טוקן לעמוד הכניסה
    return {"text": text, "url": f"https://wa.me/{_wa_number(booking.guest_phone)}?text={quote(text)}"}


@router.post("/resync-lock-windows", dependencies=[Depends(_auth)])
async def resync_lock_windows(db: AsyncSession = Depends(get_db)):
    """NEW (2.10.26): מעדכן את חלון התוקף במנעול לכל הזמנה שעוד לא יצאה ויש לה קוד —
    לתיקון קודים שנוצרו עם הסטה של 3 שעות (באג אזור זמן)."""
    from datetime import date
    from sqlalchemy import select
    from app.integrations.ttlock import update_passcode_window
    from app.models import is_cancelled_status

    rows = (await db.execute(
        select(Booking).where(Booking.check_out >= date.today(), Booking.ttlock_pwd_ids.isnot(None))
    )).scalars().all()
    out = []
    for b in rows:
        if is_cancelled_status(b.status) or not b.ttlock_pwd_ids:
            continue
        ok = await update_passcode_window(b, db)
        out.append({"id": b.id, "guest": b.guest_name, "check_in": b.check_in.isoformat(),
                    "checkin_time": b.checkin_time, "checkout_time": b.checkout_time, "updated": ok})
    return {"count": len(out), "bookings": out}


@router.get("/sms-test", dependencies=[Depends(_auth)])
async def sms_test(phone: str):
    try:
        shipment = await send_sms(phone, "בדיקת SMS — מדבר וים")
    except SmsError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "shipment_id": shipment}
