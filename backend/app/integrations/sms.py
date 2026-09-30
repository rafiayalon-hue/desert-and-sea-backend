"""
SMS דרך ספק ישראלי (019SMS) — גיבוי כשה-WhatsApp (Twilio) לא זמין,
והתראות לרפי/אבישג.

משתני סביבה ב-Railway (שירות selfless-happiness):
  SMS_019_USERNAME   שם המשתמש בחשבון 019
  SMS_019_TOKEN      טוקן API (Settings → API Token Management, מוצג פעם אחת)
  SMS_SENDER         שם שולח, עד 11 תווים, אנגלית/ספרות בלבד (ברירת מחדל: DesertSea)
  SMS_ENABLED        true/false — מתג כללי (ברירת מחדל: true אם יש טוקן)

תיעוד: https://docs.019sms.co.il/sms/send-sms.html
"""
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://019sms.co.il/api"


class SmsError(Exception):
    pass


def sms_enabled() -> bool:
    return bool(settings.sms_enabled and settings.sms_019_token and settings.sms_019_username)


def _to_local(phone: str) -> str:
    """019 מצפה ל-05XXXXXXXX. מספר ישראלי בכל פורמט → מקומי.
    מספר זר → ספרות בלבד עם קידומת מדינה (לבדוק מול 019 שיש תמיכה בחו"ל)."""
    p = re.sub(r"[^\d+]", "", phone or "")
    if p.startswith("+972"):
        return "0" + p[4:]
    if p.startswith("972"):
        return "0" + p[3:]
    return p.lstrip("+")


async def send_sms(phone: str, text: str, ref: str | None = None) -> str:
    """שולח SMS. מחזיר shipment_id. זורק SmsError בכל כשל."""
    if not sms_enabled():
        raise SmsError("SMS not configured")
    if not phone:
        raise SmsError("no phone")

    payload = {
        "sms": {
            "user": {"username": settings.sms_019_username},
            "source": settings.sms_sender[:11],
            "destinations": {"phone": [{"$": {"id": ref or ""}, "_": _to_local(phone)}]},
            "message": text[:1005],
        }
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.sms_019_token}"},
            )
        data = resp.json() if resp.content else {}
    except Exception as e:
        raise SmsError(f"request error: {e}") from e

    if resp.status_code >= 300 or str(data.get("status")) != "0":
        raise SmsError(f"019 rejected ({resp.status_code}): {data}")

    shipment = str(data.get("shipment_id", ""))
    logger.info(f"SMS sent to {_to_local(phone)} (shipment {shipment})")
    return shipment
