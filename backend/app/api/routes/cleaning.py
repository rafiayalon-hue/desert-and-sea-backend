"""
NEW (4.10.26) — יומן ניקיונות לפי לוג המנעולים (TTLock).

GET /api/cleaning?days=30

לא נשמר כלום ב-DB: בכל קריאה נשלף לוג הפתיחות משני המנעולים, מסוננות
הכניסות עם קוד המנקה (ברירת מחדל 5555, אפשר לשנות במשתנה סביבה CLEANER_CODE),
ומוצמדות ליציאות האורחים מההזמנות.

תשובה:
{
  "turnovers": [   # כל יציאת אורח (מהחדשה לישנה) + מתי נוקה
    {"cabin": "mdbr", "checkout_date": "2026-10-03", "guest_out": "...",
     "next_checkin": "2026-10-05", "guest_in": "...",
     "cleaning": {"date": "2026-10-03", "first": "12:40", "last": "15:10", "entries": 3} | null,
     "status": "done" | "missing" | "pending"}
  ],
  "other": [   # כניסות מנקה שלא קשורות ליציאת אורח
    {"cabin": "ym", "date": "2026-09-28", "first": "09:10", "last": "09:10", "entries": 1}
  ],
  "cleaner_code": "5555", "days": 30, "generated_at": "..."
}
status: done = נמצאה כניסת מנקה בין היציאה להגעה הבאה;
        missing = עבר מועד ההגעה הבאה (או 3 ימים) ואין כניסה;
        pending = עוד לא הגיע הזמן.
"""
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.booking import Booking, is_cancelled_status
from app.api.routes.ha import _cabins_for

router = APIRouter(prefix="/api/cleaning", tags=["cleaning"])

TZ = ZoneInfo("Asia/Jerusalem")
CABIN_LOCK = {"mdbr": "desert", "ym": "sea"}
CABIN_NAME = {"mdbr": "מדבר", "ym": "ים"}
PASSCODE_UNLOCK = 4  # recordType של פתיחה בקוד


def _cleaner_code() -> str:
    return (os.getenv("CLEANER_CODE") or "5555").strip().rstrip("#")


@router.get("")
async def cleaning_log(days: int = 30, db: AsyncSession = Depends(get_db)):
    from app.integrations.ttlock import LOCK_IDS, list_lock_records

    days = max(1, min(days, 90))
    now = datetime.now(TZ)
    today = now.date()
    start = today - timedelta(days=days)
    code = _cleaner_code()

    # ── 1. כניסות מנקה מהמנעולים, מקובצות לפי צימר + יום ─────────────────
    start_ms = int(datetime.combine(start, datetime.min.time(), TZ).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    visits: dict[tuple[str, date], list[datetime]] = defaultdict(list)
    errors = {}
    for cabin, lock_key in CABIN_LOCK.items():
        try:
            recs = await list_lock_records(LOCK_IDS[lock_key], start_ms, end_ms)
        except Exception as e:
            errors[cabin] = str(e)[:200]
            continue
        for r in recs:
            if str(r.get("keyboardPwd") or "").rstrip("#") != code:
                continue
            if r.get("success") not in (1, True, None):
                continue
            t = datetime.fromtimestamp(r["lockDate"] / 1000, TZ)
            visits[(cabin, t.date())].append(t)

    def _visit(cabin: str, d: date) -> dict | None:
        ts = sorted(visits.get((cabin, d), []))
        if not ts:
            return None
        return {"date": d.isoformat(), "first": ts[0].strftime("%H:%M"),
                "last": ts[-1].strftime("%H:%M"), "entries": len(ts)}

    # ── 2. הזמנות בטווח (וקצת אחריו, בשביל "ההגעה הבאה") ─────────────────
    rows = (await db.execute(
        select(Booking).where(Booking.check_out >= start, Booking.check_in <= today + timedelta(days=60))
    )).scalars().all()
    per_cabin: dict[str, list] = defaultdict(list)
    for b in rows:
        if is_cancelled_status(b.status):
            continue
        for c in _cabins_for(b.room_name):
            per_cabin[c].append(b)

    turnovers = []
    used: set[tuple[str, date]] = set()
    for cabin, bks in per_cabin.items():
        bks.sort(key=lambda b: b.check_in)
        for b in bks:
            co = b.check_out
            if co < start or co > today:
                continue
            nxt = next((n for n in bks if n.check_in >= co and n.id != b.id), None)
            window_end = nxt.check_in if nxt else co + timedelta(days=3)
            found = None
            d = co
            while d <= min(window_end, today):
                v = _visit(cabin, d)
                if v:
                    found = v
                    used.add((cabin, d))
                    break
                d += timedelta(days=1)
            if found:
                status = "done"
            elif today > window_end or (today == window_end and nxt and now.hour >= 14):
                status = "missing"
            else:
                status = "pending"
            turnovers.append({
                "cabin": cabin,
                "cabin_name": CABIN_NAME[cabin],
                "checkout_date": co.isoformat(),
                "checkout_time": b.checkout_time,
                "guest_out": b.guest_name,
                "booking_out_id": b.id,
                "next_checkin": nxt.check_in.isoformat() if nxt else None,
                "guest_in": nxt.guest_name if nxt else None,
                "booking_in_id": nxt.id if nxt else None,
                "cleaning": found,
                "status": status,
            })
    turnovers.sort(key=lambda t: (t["checkout_date"], t["cabin"]), reverse=True)

    other = []
    for (cabin, d) in sorted(visits, key=lambda k: k[1], reverse=True):
        if (cabin, d) in used:
            continue
        v = _visit(cabin, d)
        other.append({"cabin": cabin, "cabin_name": CABIN_NAME[cabin], **v})

    return {
        "turnovers": turnovers,
        "other": other,
        "errors": errors,
        "cleaner_code": code,
        "days": days,
        "generated_at": now.isoformat(timespec="seconds"),
    }
