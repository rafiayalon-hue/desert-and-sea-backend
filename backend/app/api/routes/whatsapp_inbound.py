"""
Twilio WhatsApp inbound webhook.

זה שונה מ-webhook.py (שם: מיניהוטל, JSON) — Twilio שולח הודעות נכנסות
כ-form-data רגיל (application/x-www-form-urlencoded), לא JSON.
Docs: https://www.twilio.com/docs/messaging/guides/webhook-request

זה ה-URL שצריך להזין ב-Twilio Console → WhatsApp Senders → Edit Sender →
"Webhook URL for incoming messages".
"""
import logging

from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking, MessageLog

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_phone(phone: str) -> str:
    """זהה ל-normalize_phone ב-guests.py — כדי שהתאמה לפי טלפון תהיה עקבית
    בכל המקומות בקוד. p מגיע מ-Twilio בפורמט whatsapp:+972XXXXXXXXX."""
    p = (phone or "").replace("whatsapp:", "").strip().replace("-", "").replace(" ", "")
    if p.startswith("+972"):
        p = "0" + p[4:]
    elif p.startswith("972"):
        p = "0" + p[3:]
    return p


@router.post("/whatsapp-inbound")
async def whatsapp_inbound(
    From: str = Form(...),
    Body: str = Form(""),
    MessageSid: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    מקבל הודעה נכנסת מ-Twilio. תמיד מחזיר 200 (גם אם לא נמצאה הזמנה
    תואמת) — אחרת Twilio ינסה שוב ושוב לפי מדיניות ה-retry שלו, בלי
    שזה יעזור (ההודעה עצמה לא תשתנה בניסיון הבא).
    """
    raw_phone = From
    normalized = _normalize_phone(raw_phone)

    # מנסים לשייך להזמנה קיימת לפי טלפון — כדי שהשיחה תופיע תחת האורח
    # הנכון בדשבורד. אם לא נמצא (מספר לא מוכר) — עדיין שומרים את ההודעה,
    # רק בלי booking_id, כדי לא לאבד אותה.
    result = await db.execute(select(Booking).where(Booking.guest_phone.isnot(None)))
    all_bookings = result.scalars().all()
    matched = next(
        (b for b in all_bookings if _normalize_phone(b.guest_phone or "") == normalized),
        None,
    )

    log = MessageLog(
        booking_id=matched.id if matched else None,
        phone=raw_phone.replace("whatsapp:", ""),
        message_type="reply",
        body=Body,
        status="received",
        twilio_sid=MessageSid,
        direction="inbound",
    )
    db.add(log)
    await db.commit()

    logger.info(f"WhatsApp inbound from {raw_phone}: matched_booking={matched.id if matched else None}")

    # Twilio מצפה ל-TwiML (גם ריק) בתגובה — לא JSON. Response ריק עם
    # content-type נכון מספיק; אין צורך לענות אוטומטית להודעה.
    return Response(content="<Response></Response>", media_type="application/xml")
