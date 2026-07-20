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
    כל הקמפיינים שנרשמו, כל אחד עם תוצאות מחושבות בזמן אמת: כמה
    הזמנות ישירות/מהאתר "נכנסו" (synced_at) בטווח התאריכים של הקמפיין,
    וסך ההכנסה שלהן. קירוב, לא ייחוס מדויק — אבל מספיק לראות מגמה.
    """
    result = await db.execute(select(Campaign).order_by(Campaign.start_date.desc()))
    campaigns = result.scalars().all()

    all_bookings_result = await db.execute(
        select(Booking).where(Booking.source.in_(["direct", "website"]))
    )
    relevant_bookings = all_bookings_result.scalars().all()

    output = []
    for c in campaigns:
        start_dt = datetime.combine(c.start_date, datetime.min.time())
        end_dt = datetime.combine(c.end_date, datetime.max.time())
        matched = [
            b for b in relevant_bookings
            if b.synced_at and start_dt <= b.synced_at <= end_dt
            and "cancel" not in (b.status or "").lower()
        ]
        output.append({
            "id": c.id,
            "name": c.name,
            "platform": c.platform,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat(),
            "budget": float(c.budget) if c.budget is not None else None,
            "notes": c.notes,
            "bookings_count": len(matched),
            "revenue": sum(b.total_price or 0 for b in matched),
        })
    return output
