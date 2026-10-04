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
    # "Sesert" = שגיאת כתיב קיימת ב-MiniHotel לצימר מדבר
    if "des" in r or "sesert" in r or "מדבר" in r:
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

    debug = []
    for b in bookings:
        cabins = _cabins_for(b.room_name)
        debug.append({
            "id": b.id,
            "room_name": b.room_name,
            "status": b.status,
            "check_in": b.check_in.isoformat(),
            "check_out": b.check_out.isoformat(),
            "matched": cabins,
        })
        if is_cancelled_status(b.status):
            continue
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
    result["bookings_today"] = debug  # לאבחון: מה נמצא היום ואיך זוהה
    return result


# ---------------------------------------------------------------------------
# NEW (3.10.26): מצב סוללה של מנעולי TTLock — ל-HA (התראת סוללה נמוכה)
# GET /api/ha/locks  →  {"mdbr": {"battery": 30}, "ym": {"battery": 85}, ...}
# ---------------------------------------------------------------------------
@router.get("/locks")
async def locks_status(x_ha_token: str | None = Header(default=None)):
    _check_token(x_ha_token)
    from app.integrations.ttlock import LOCK_IDS, get_lock_status, query_open_state

    names = {"desert": "mdbr", "sea": "ym"}
    out = {}
    for key, lock_id in LOCK_IDS.items():
        k = names.get(key, key)
        try:
            d = await get_lock_status(lock_id)
            out[k] = {
                "battery": d.get("electricQuantity"),
                "name": d.get("lockAlias") or d.get("lockName"),
                "ok": True,
            }
        except Exception as e:
            out[k] = {"battery": None, "ok": False, "error": str(e)[:120]}
        # NEW (4.10.26): זמינות חיה דרך הגייטווי (מצב שבת / סוללה מתה → false)
        live = await query_open_state(lock_id)
        out[k]["reachable"] = live["reachable"]
        out[k]["reach_error"] = live["error"]
    out["generated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    return out


# ---------------------------------------------------------------------------
# NEW (4.10.26): לוג פתיחות — לבדיקה (קריאה בלבד)
# GET /api/ha/lock-records?days=7
# ---------------------------------------------------------------------------
@router.get("/lock-records")
async def lock_records(days: int = 7, x_ha_token: str | None = Header(default=None)):
    _check_token(x_ha_token)
    from app.integrations.ttlock import LOCK_IDS, list_lock_records

    now_ms = int(datetime.now(TZ).timestamp() * 1000)
    start_ms = now_ms - min(days, 60) * 86400 * 1000
    names = {"desert": "mdbr", "sea": "ym"}
    out = {}
    for key, lock_id in LOCK_IDS.items():
        try:
            recs = await list_lock_records(lock_id, start_ms, now_ms)
            out[names.get(key, key)] = [
                {
                    "time": datetime.fromtimestamp(r.get("lockDate", 0) / 1000, TZ).strftime("%d.%m %H:%M"),
                    "type": r.get("recordType"),
                    "code": r.get("keyboardPwd"),
                    "user": r.get("username"),
                    "success": r.get("success"),
                }
                for r in sorted(recs, key=lambda x: x.get("lockDate", 0), reverse=True)
            ]
        except Exception as e:
            out[names.get(key, key)] = {"error": str(e)[:200]}
    return out
