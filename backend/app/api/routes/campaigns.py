"""
קמפיינים — כלים לפנייה יזומה לאורחים (לא הודעות אוטומטיות דרך Twilio,
כי הודעות שיווק דורשות תבנית Marketing מאושרת שאין לנו עדיין — ראו
השיחה מ-17.7.26). המטרה: לרכז רשימה נגישה לפנייה אישית ידנית, מהטלפון
של רפי/אבישג עצמם.

NEW (18.7.26): גם מעקב קל אחרי קמפיינים שיווקיים (FB/IG) — מיועד
לאבישג, פשוט ונטול חיכוך: שם, פלטפורמה, תאריכים, תקציב. התוצאות
(הזמנות ישירות/הכנסה בטווח) מחושבות בזמן אמת מול bookings.synced_at
כקירוב ל"מתי ההזמנה בוצעה בפועל" — לא מדויק מדעית, אבל מספיק כדי
לראות אם קמפיין הזיז משהו.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Date, Integer, Numeric, String, Text, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, Base
from app.models import Booking

router = APIRouter()


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    platform = Column(String(50))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget = Column(Numeric(10, 2))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class CampaignCreate(BaseModel):
    name: str
    platform: str | None = None
    start_date: date
    end_date: date
    budget: float | None = None
    notes: str | None = None


def _normalize_phone(phone: str) -> str:
    p = (phone or "").strip().replace("-", "").replace(" ", "")
    if p.startswith("+972"):
        p = "0" + p[4:]
    elif p.startswith("972"):
        p = "0" + p[3:]
    return p


@router.get("/winback")
async def winback_list(months_back: int = 12, db: AsyncSession = Depends(get_db)):
    """
    אורחים ש: יצאו בעבר (עד שנה אחורה כברירת מחדל), ההזמנה לא בוטלה,
    יש להם טלפון או מייל, ו-**אין** להם שום הזמנה עתידית קיימת (לא
    לפנות למי שכבר הזמין קדימה — לפי הדרישה המפורשת).
    """
    today = date.today()
    cutoff = today - timedelta(days=months_back * 30)

    all_result = await db.execute(select(Booking))
    all_bookings = all_result.scalars().all()

    def is_cancelled(b):
        return "cancel" in (b.status or "").lower()

    # מפתחות (טלפון מנורמל, מייל) של כל מי שיש לו הזמנה עתידית — נפסול
    # אותם מהרשימה גם אם יש להם גם שהות עבר.
    future_phones = set()
    future_emails = set()
    for b in all_bookings:
        if b.check_in and b.check_in >= today and not is_cancelled(b):
            if b.guest_phone:
                future_phones.add(_normalize_phone(b.guest_phone))
            if b.guest_email:
                future_emails.add(b.guest_email.strip().lower())

    # מועמדים: שהות עבר בטווח, לא מבוטלת, יש דרך ליצור קשר
    candidates = []
    for b in all_bookings:
        if not b.check_out or b.check_out >= today or b.check_out < cutoff:
            continue
        if is_cancelled(b):
            continue
        phone_norm = _normalize_phone(b.guest_phone) if b.guest_phone else None
        email_norm = b.guest_email.strip().lower() if b.guest_email else None
        if not phone_norm and not email_norm:
            continue
        if phone_norm and phone_norm in future_phones:
            continue
        if email_norm and email_norm in future_emails:
            continue
        candidates.append(b)

    # דה-דופליקציה — לפי טלפון קודם, מייל כ-fallback (כמו ב-useGuests.js
    # בפרונט) — שומרים רק את השהות האחרונה ביותר לכל אורח ייחודי.
    dedup: dict[str, Booking] = {}
    for b in sorted(candidates, key=lambda x: x.check_out):
        key = _normalize_phone(b.guest_phone) if b.guest_phone else f"email:{b.guest_email.strip().lower()}"
        dedup[key] = b  # הכי מאוחר דורס (בזכות המיון)

    result = [
        {
            "guest_name": b.guest_name,
            "phone": b.guest_phone,
            "email": b.guest_email,
            "last_checkout": b.check_out.isoformat() if b.check_out else None,
            "last_room": b.room_name,
        }
        for b in dedup.values()
    ]
    result.sort(key=lambda r: r["last_checkout"] or "", reverse=True)
    return result


# ---------------------------------------------------------------------------
# מעקב קמפיינים (NEW 18.7.26)
# ---------------------------------------------------------------------------

@router.post("/")
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(**data.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="קמפיין לא נמצא")
    await db.delete(campaign)
    await db.commit()
    return {"status": "deleted"}


@router.get("/list")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    """
    כל הקמפיינים, עם תוצאות מחושבות בזמן אמת.

    REWRITE (20.9.26): עד עכשיו נמדד לפי synced_at — אבל synced_at מתעדכן
    בכל שינוי בהזמנה (וכל 352 ההזמנות מייבוא האקסל קיבלו אותו תאריך), כך
    שהמספרים היו חסרי משמעות. עכשיו נמדד לפי created_at — מתי ההזמנה
    נכנסה לראשונה — ומושווה לקצב "רגיל" ב-8 השבועות שלפני הקמפיין.

    מה נספר:
      - הזמנות שנוצרו בטווח (ישיר + אתר), לא מבוטלות; לילות, הכנסה.
      - לילה בודד למשפחה (ילדים>0 או 4+ נפשות) — עסקה לא רצויה, מסומנת.
      - הזמנות Airbnb בטווח — לידיעה (קמפיין כללי יכול להזיז גם אותן).
      - פניות וואטסאפ נכנסות בטווח: מספרים שונים, ומתוכם חדשים
        (טלפון שלא הופיע אף פעם בהזמנה).
      - קצב בסיס: הזמנות ישירות לשבוע ב-8 השבועות שלפני ההתחלה
        (None אם אין מספיק נתוני created_at לתקופה הזו).
    """
    from app.models import MessageLog  # import מקומי — למנוע תלות מעגלית

    result = await db.execute(select(Campaign).order_by(Campaign.start_date.desc()))
    campaigns = result.scalars().all()

    all_bookings = (await db.execute(select(Booking))).scalars().all()
    known_phones = {_normalize_phone(b.guest_phone) for b in all_bookings if b.guest_phone}
    first_booking_by_phone: dict[str, datetime] = {}
    for b in all_bookings:
        if b.guest_phone and b.created_at:
            k = _normalize_phone(b.guest_phone)
            if k not in first_booking_by_phone or b.created_at < first_booking_by_phone[k]:
                first_booking_by_phone[k] = b.created_at

    inbound = (await db.execute(
        select(MessageLog).where(MessageLog.direction == "inbound")
    )).scalars().all()

    earliest_created = min((b.created_at for b in all_bookings if b.created_at), default=None)

    def is_cancelled(b):
        return "cancel" in (b.status or "").lower()

    def is_direct(b):
        return (b.source or "direct").lower() in ("direct", "website", "homepage")

    def nights(b):
        return (b.check_out - b.check_in).days if b.check_in and b.check_out else 0

    output = []
    for c in campaigns:
        start_dt = datetime.combine(c.start_date, datetime.min.time())
        end_dt = datetime.combine(c.end_date, datetime.max.time())
        in_window = [b for b in all_bookings
                     if b.created_at and start_dt <= b.created_at <= end_dt and not is_cancelled(b)]
        direct = [b for b in in_window if is_direct(b)]
        airbnb = [b for b in in_window if (b.source or "").lower() == "airbnb"]
        one_night_family = [b for b in direct if nights(b) == 1
                            and ((b.children or 0) > 0 or (b.adults or 0) + (b.children or 0) >= 4)]

        # פניות וואטסאפ נכנסות בטווח
        phones_in_window = {_normalize_phone(m.phone) for m in inbound
                            if m.created_at and start_dt <= m.created_at <= end_dt and m.phone}
        new_phones = {p for p in phones_in_window
                      if p not in known_phones
                      or (p in first_booking_by_phone and first_booking_by_phone[p] >= start_dt)}

        # קצב בסיס — 8 שבועות לפני ההתחלה
        base_start = start_dt - timedelta(weeks=8)
        baseline_per_week = None
        if earliest_created and earliest_created <= base_start:
            base = [b for b in all_bookings if b.created_at and base_start <= b.created_at < start_dt
                    and not is_cancelled(b) and is_direct(b)]
            baseline_per_week = round(len(base) / 8, 1)

        today_dt = datetime.utcnow()
        eff_end = min(end_dt, today_dt)
        weeks = max((eff_end - start_dt).days / 7, 1 / 7) if eff_end > start_dt else 0
        per_week = round(len(direct) / weeks, 1) if weeks else 0

        output.append({
            "id": c.id,
            "name": c.name,
            "platform": c.platform,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat(),
            "budget": float(c.budget) if c.budget is not None else None,
            "notes": c.notes,
            "bookings_count": len(direct),
            "revenue": float(sum(b.total_price or 0 for b in direct)),
            "nights": sum(nights(b) for b in direct),
            "one_night_family": len(one_night_family),
            "airbnb_count": len(airbnb),
            "inquiries": len(phones_in_window),
            "new_inquiries": len(new_phones),
            "per_week": per_week,
            "baseline_per_week": baseline_per_week,
            "status": "upcoming" if start_dt > today_dt else ("active" if end_dt >= today_dt else "ended"),
        })
    return output
