from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.integrations.whatsapp import build_message, send_whatsapp, send_whatsapp_template
from app.models import Booking, Guest, MessageLog
router = APIRouter()

# NEW (17.7.26): מיפוי בין סוגי ההודעות כפי שה-dashboard (BookingDetail.jsx)
# מכיר אותן, לבין מפתחות CONTENT_SIDS ב-whatsapp.py (שם התבניות
# המאושרות בפועל ב-Twilio). "review_request" נשאר בחוץ בכוונה — אין לו
# עדיין תבנית מאושרת, אז ממשיך להישלח כטקסט חופשי (עובד רק אם יש חלון
# שירות פתוח של 24 שעות עם האורח — אחרת יידחה בשקט ע"י Meta).
DASHBOARD_TO_TEMPLATE = {
    "booking_confirmation": "confirmation",
    "pre_arrival": "pre_arrival",
    "checkin_code": "entry_code",
    "checkout_payment": "checkout",
}


class SendMessageRequest(BaseModel):
    phone: str
    body: str
    booking_id: int | None = None
    guest_id: int | None = None
    message_type: str = "manual"
class CampaignRequest(BaseModel):
    template_key: str
    guest_ids: list[int]
    extra: dict = {}
@router.get("/")
async def list_messages(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(MessageLog).order_by(MessageLog.created_at.desc()))
    return result.all()
@router.post("/send")
async def send_message(req: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    template_key = DASHBOARD_TO_TEMPLATE.get(req.message_type)

    # NEW (17.7.26): אם זה אחד מ-4 סוגי ההודעות עם תבנית מאושרת, ויש לנו
    # booking_id לבנות ממנו את המשתנים — שולחים דרך content_sid, לא
    # טקסט חופשי. משתמשים באותה פונקציית build_variables שה-scheduler
    # האוטומטי כבר משתמש בה, כדי שלא יהיו שני מקומות שבונים משתנים
    # בצורה שונה לאותה תבנית.
    if template_key and req.booking_id:
        from app.scheduler import _build_variables  # local import: מונע circular import בטעינת המודול

        booking = await db.get(Booking, req.booking_id)
        if not booking:
            raise HTTPException(status_code=404, detail="הזמנה לא נמצאה")

        try:
            variables = await _build_variables(template_key, booking, db)
            sid = send_whatsapp_template(req.phone, template_key, variables)
            status = "sent"
        except Exception as e:
            sid = None
            status = "failed"
    else:
        # נתיב ישן: טקסט חופשי — פועל רק בתוך חלון שירות פתוח של 24 שעות.
        try:
            sid = send_whatsapp(req.phone, req.body)
            status = "sent"
        except Exception as e:
            sid = None
            status = "failed"

    log = MessageLog(
        booking_id=req.booking_id,
        guest_id=req.guest_id,
        phone=req.phone,
        message_type=req.message_type,
        body=req.body,
        status=status,
        twilio_sid=sid,
    )
    db.add(log)
    await db.commit()
    return {"status": status, "twilio_sid": sid}
@router.post("/campaign")
async def send_campaign(req: CampaignRequest, db: AsyncSession = Depends(get_db)):
    """Send a templated message to a list of returning guests."""
    results = []
    for guest_id in req.guest_ids:
        guest = await db.get(Guest, guest_id)
        if not guest:
            continue
        body = build_message(req.template_key, guest.language, name=guest.name, **req.extra)
        try:
            sid = send_whatsapp(guest.phone, body)
            status = "sent"
        except Exception:
            sid = None
            status = "failed"
        log = MessageLog(
            guest_id=guest_id,
            phone=guest.phone,
            message_type="campaign",
            body=body,
            status=status,
            twilio_sid=sid,
        )
        db.add(log)
        results.append({"guest_id": guest_id, "status": status})
    await db.commit()
    return {"sent": len(results), "results": results}
