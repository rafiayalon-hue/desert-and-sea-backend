"""
ממשק ל-Home Assistant — מצב תפוס/פנוי של הצימרים לפי ההזמנות.

GET /api/ha/occupancy
Header: X-HA-Token: <HA_TOKEN>   (משתנה סביבה ב-Railway)

תשובה לדוגמה:
{
  "ym":   {"occupied": true,  "arriving_today": false, "departing_today": true,  "check_out": "2026-09-30"},
  "mdbr": {"occupied": false, "arriving_today": true,  "departing_today": false, "check_out": null},
  "generated_at": "2026-09-28T14:05:00+03:00"
}

"תפוס" = יש הזמנה פעילה (לא מבוטלת) שהשעה הנוכחית בין שעת ההגעה ביום
ה-check_in לשעת העזיבה ביום ה-check_out. ברירות מחדל: הגעה 14:00, עזיבה 12:00
(אם בהזמנה יש checkin_time / checkout_time — הם גוברים).
"""
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db  # ← לוודא שזה אותו import שמופיע ב-routes האחרים
from app.models.booking import Booking, is_cancelled_status  # ← לוודא את שם הקובץ של המודל

router = APIRouter(prefix="/api/ha", tags=["home-assistant"])

TZ = ZoneInfo("Asia/Jerusalem")
DEFAULT_CHECKIN = time(14, 0)
DEFAULT_CHECKOUT = time(12, 0)


def _check_token(x_ha_token: str | None) -> None:
    expected = os.getenv("HA_TOKEN")
    if not expected or x_ha_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _parse_time(value: str | None, default: time) -> time:
    if not value:
        return default
    try:
        h, m = value.strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return default


def _cabins_for(room_name: str | None) -> list[str]:
    """ממפה room_name לצימרים. des_sea = שני הצימרים."""
    r = (room_name or "").lower()
    if "des_sea" in r or ("sea" in r and "des" in r):
        return ["ym", "mdbr"]
    if "sea" in r or "ים" in r:
        return ["ym"]
    if "des" in r or "מדבר" in r:
        return ["mdbr"]
    return []


@router.get("/occupancy")
async def occupancy(
    x_ha_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    _check_token(x_ha_token)

    now = datetime.now(TZ)
    today = now.date()

    result = {
        c: {"occupied": False, "arriving_today": False, "departing_today": False, "check_out": None}
        for c in ("ym", "mdbr")
    }

    rows = await db.execute(
        select(Booking).where(Booking.check_in <= today, Booking.check_out >= today)
    )
    bookings = rows.scalars().all()

    for b in bookings:
        if is_cancelled_status(b.status):
            continue
        cabins = _cabins_for(b.room_name)
        if not cabins:
            continue

        start = datetime.combine(b.check_in, _parse_time(b.checkin_time, DEFAULT_CHECKIN), TZ)
        end = datetime.combine(b.check_out, _parse_time(b.checkout_time, DEFAULT_CHECKOUT), TZ)

        for c in cabins:
            if b.check_in == today:
                result[c]["arriving_today"] = True
            if b.check_out == today:
                result[c]["departing_today"] = True
            if start <= now < end:
                result[c]["occupied"] = True
                result[c]["check_out"] = b.check_out.isoformat()

    result["generated_at"] = now.isoformat(timespec="seconds")
    return result
