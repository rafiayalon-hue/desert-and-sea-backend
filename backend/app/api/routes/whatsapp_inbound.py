"""
Twilio WhatsApp inbound webhook.

זה שונה מ-webhook.py (שם: מיניהוטל, JSON) — Twilio שולח הודעות נכנסות
כ-form-data רגיל (application/x-www-form-urlencoded), לא JSON.
Docs: https://www.twilio.com/docs/messaging/guides/webhook-request

זה ה-URL שצריך להזין ב-Twilio Console → WhatsApp Senders → Edit Sender →
"Webhook URL for incoming messages".
"""
import logging

import httpx
from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.integrations.whatsapp import _to_e164
from app.models import Booking, MessageLog
from app.models.business_settings import BusinessSettings

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


async def _send_sms_notification(to_number: str, body: str) -> None:
    """
    שולח SMS התראה קצר. best-effort בלבד — כשל בשליחת ה-SMS לא אמור
    לגרום ל-500 על ה-webhook עצמו (Twilio ינסה שוב לשלוח את ה-WhatsApp
    inbound event אם נקבל שגיאה, וזה לא הבעיה שצריך לתקן בניסיון הבא).
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_sms_from:
        logger.warning("SMS notification skipped: Twilio SMS not configured (twilio_sms_from missing)")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={"From": settings.twilio_sms_from, "To": to_number, "Body": body},
            )
            if resp.status_code >= 300:
                logger.error(f"SMS notification failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.error(f"SMS notification error: {e}")


async def _notify_owners_of_inbound(guest_name: str | None, phone: str, body: str, db: AsyncSession) -> None:
    """שולח SMS לרפי ולאבישג (לפי business_settings) שהודעה חדשה הגיעה."""
    result = await db.execute(select(BusinessSettings).where(BusinessSettings.id == 1))
    biz = result.scalar_one_or_none()
    if not biz:
        return

    who = guest_name or phone
    preview = body[:100] + ("…" if len(body) > 100 else "")
    sms_body = f"הודעת WhatsApp חדשה מ-{who}:\n{preview}"

    for owner_phone in (biz.owner1_phone, biz.owner2_phone):
        if owner_phone:
            await _send_sms_notification(_to_e164(owner_phone), sms_body)


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

    # NEW (17.7.26): התראת SMS לרפי ואבישג — כדי שידעו גם כשלא ליד המחשב.
    await _notify_owners_of_inbound(
        guest_name=matched.guest_name if matched else None,
        phone=raw_phone.replace("whatsapp:", ""),
        body=Body,
        db=db,
    )

    # Twilio מצפה ל-TwiML (גם ריק) בתגובה — לא JSON. Response ריק עם
    # content-type נכון מספיק; אין צורך לענות אוטומטית להודעה.
    return Response(content="<Response></Response>", media_type="application/xml")
