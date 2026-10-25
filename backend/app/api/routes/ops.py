"""
NEW (25.10.26) — לוח תפעול: הכנת צימר להגעה + תשלום וקבלה אחרי יציאה.

GET   /api/ops/board          הגעות קרובות (עם רשימת הכנה) + יציאות שממתינות לתשלום/קבלה
PATCH /api/ops/{booking_id}   עדכון מצב הכנה / סימון פריט / תשורה / תשלום / קבלה

כל הסימונים ידניים (אתם בלבד). זיהוי "המנקה נכנס" מגיע מ-/api/cleaning
(לוג המנעולים) ומוצג בצד הלקוח — כאן לא קוראים ל-TTLock בכלל.

כללים:
  * מצב הכנה: dirty (ברירת מחדל) → partial → clean.
    כל הפריטים החובה מסומנים → clean אוטומטית. הוסר סימון מ-clean → partial.
    פריטי חובה: milk, notes, inspected (+ gift אם gift_needed). balconies — אופציונלי.
  * תשלום: unpaid / link_sent / paid. ב-Airbnb אין link_sent (מקבלים העברה).
  * הזמנה נעלמת מרשימת התשלומים רק כש-paid וגם receipt_issued.
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.ha import _cabins_for
from app.database import get_db
from app.models.booking import Booking, is_cancelled_status
from app.models.booking_ops import BookingOps
from app.services.booking_guard import get_milk, norm_phone

router = APIRouter(prefix="/api/ops", tags=["ops"])

TZ = ZoneInfo("Asia/Jerusalem")
CABIN_NAME = {"mdbr": "מדבר", "ym": "ים"}

PREP_STATUSES = {"dirty", "partial", "clean"}
PAY_STATUSES = {"unpaid", "link_sent", "paid"}
CHECK_KEYS = ("milk", "notes", "balconies", "gift", "inspected")
REQUIRED_BASE = ("milk", "notes", "inspected")

ARRIVAL_HORIZON_DAYS = 10     # הגעות קרובות שמוצגות בלוח
PAYMENT_LOOKBACK_DAYS = 45    # יציאות אחרונות שעדיין פתוחות
PAYMENT_LOOKAHEAD_DAYS = 2    # יציאות שמתקרבות (הקישור יישלח בעזיבה)


def _load_checklist(ops: BookingOps | None) -> dict:
    if ops is None or not ops.checklist:
        return {}
    try:
        data = json.loads(ops.checklist)
        return {k: bool(v) for k, v in data.items() if k in CHECK_KEYS}
    except Exception:
        return {}


def _ops_state(ops: BookingOps | None) -> dict:
    return {
        "prep_status": (ops.prep_status if ops else None) or "dirty",
        "checklist": _load_checklist(ops),
        "gift_needed": bool(ops.gift_needed) if ops else False,
        "pay_status": (ops.pay_status if ops else None) or "unpaid",
        "receipt_issued": bool(ops.receipt_issued) if ops else False,
    }


def _num(v) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


@router.get("/board")
async def board(db: AsyncSession = Depends(get_db)):
    today = datetime.now(TZ).date()
    horizon = today + timedelta(days=ARRIVAL_HORIZON_DAYS)

    bookings = [
        b for b in (await db.execute(select(Booking))).scalars().all()
        if not is_cancelled_status(b.status) and b.check_in and b.check_out
    ]
    ops_rows = {o.booking_id: o for o in (await db.execute(select(BookingOps))).scalars().all()}

    by_phone: dict[str, list[Booking]] = defaultdict(list)
    per_cabin: dict[str, list[Booking]] = defaultdict(list)
    for b in bookings:
        p = norm_phone(b.guest_phone)
        if p:
            by_phone[p].append(b)
        for c in _cabins_for(b.room_name):
            per_cabin[c].append(b)

    # ── הגעות קרובות ─────────────────────────────────────────────────────
    arrivals = []
    for b in bookings:
        if not (today <= b.check_in <= horizon):
            continue
        cabins = _cabins_for(b.room_name)

        p = norm_phone(b.guest_phone)
        is_returning = bool(p) and any(
            o.id != b.id and o.check_out <= b.check_in for o in by_phone.get(p, [])
        )

        # מי היה בצימר לפני — והאם כבר התפנה
        prev = []
        for c in cabins:
            before = [o for o in per_cabin[c] if o.id != b.id and o.check_out <= b.check_in]
            if before:
                last = max(before, key=lambda o: o.check_out)
                prev.append({
                    "cabin": CABIN_NAME.get(c, c),
                    "guest": last.guest_name,
                    "check_out": last.check_out.isoformat(),
                    "vacated": last.check_out < today,
                })

        arrivals.append({
            "booking_id": b.id,
            "guest_name": b.guest_name,
            "cabins": [CABIN_NAME.get(c, c) for c in cabins] or [b.room_name or "?"],
            "check_in": b.check_in.isoformat(),
            "check_out": b.check_out.isoformat(),
            "nights": (b.check_out - b.check_in).days,
            "adults": b.adults,
            "children": b.children,
            "source": b.source,
            "is_returning": is_returning,
            "milk": get_milk(b),
            "prev": prev,
            **_ops_state(ops_rows.get(b.id)),
        })
    arrivals.sort(key=lambda a: (a["check_in"], a["cabins"]))

    # ── יציאות: תשלום + קבלה ─────────────────────────────────────────────
    lo = today - timedelta(days=PAYMENT_LOOKBACK_DAYS)
    hi = today + timedelta(days=PAYMENT_LOOKAHEAD_DAYS)
    payments = []
    for b in bookings:
        if not (lo <= b.check_out <= hi):
            continue
        state = _ops_state(ops_rows.get(b.id))
        if state["pay_status"] == "paid" and state["receipt_issued"]:
            continue
        payments.append({
            "booking_id": b.id,
            "guest_name": b.guest_name,
            "cabins": [CABIN_NAME.get(c, c) for c in _cabins_for(b.room_name)] or [b.room_name or "?"],
            "check_in": b.check_in.isoformat(),
            "check_out": b.check_out.isoformat(),
            "source": b.source,
            "is_airbnb": (b.source or "").strip().lower() == "airbnb",
            "total_price": _num(b.total_price),
            "balance": _num(b.balance),
            "has_phone": bool(norm_phone(b.guest_phone)),
            "pay_status": state["pay_status"],
            "receipt_issued": state["receipt_issued"],
        })
    payments.sort(key=lambda x: x["check_out"])

    return {
        "today": today.isoformat(),
        "arrivals": arrivals,
        "payments": payments,
    }


class OpsUpdate(BaseModel):
    prep_status: str | None = None
    checklist: dict[str, bool] | None = None
    gift_needed: bool | None = None
    pay_status: str | None = None
    receipt_issued: bool | None = None


@router.patch("/{booking_id}")
async def update_ops(booking_id: int, data: OpsUpdate, db: AsyncSession = Depends(get_db)):
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")

    ops = await db.get(BookingOps, booking_id)
    if ops is None:
        ops = BookingOps(
            booking_id=booking_id, prep_status="dirty", checklist="{}",
            gift_needed=False, pay_status="unpaid", receipt_issued=False,
        )
        db.add(ops)

    if data.prep_status is not None:
        if data.prep_status not in PREP_STATUSES:
            raise HTTPException(status_code=400, detail="מצב הכנה לא תקין")
        ops.prep_status = data.prep_status

    if data.pay_status is not None:
        if data.pay_status not in PAY_STATUSES:
            raise HTTPException(status_code=400, detail="מצב תשלום לא תקין")
        ops.pay_status = data.pay_status

    if data.receipt_issued is not None:
        ops.receipt_issued = data.receipt_issued

    checklist_touched = False
    if data.checklist:
        cl = _load_checklist(ops)
        for k, v in data.checklist.items():
            if k in CHECK_KEYS:
                cl[k] = bool(v)
                checklist_touched = True
        ops.checklist = json.dumps(cl, ensure_ascii=False)

    if data.gift_needed is not None:
        ops.gift_needed = data.gift_needed
        checklist_touched = True

    # הכנה: חישוב מצב אוטומטי — רק אם לא נבחר מצב ידנית באותה בקשה
    if checklist_touched and data.prep_status is None:
        cl = _load_checklist(ops)
        required = REQUIRED_BASE + (("gift",) if ops.gift_needed else ())
        if all(cl.get(k) for k in required):
            ops.prep_status = "clean"
        elif ops.prep_status == "clean":
            ops.prep_status = "partial"
        elif ops.prep_status == "dirty" and any(cl.values()):
            ops.prep_status = "partial"

    await db.commit()
    await db.refresh(ops)
    return _ops_state(ops)
