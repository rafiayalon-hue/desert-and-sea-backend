"""
Twilio WhatsApp integration for sending messages to guests.

הודעות שהעסק יוזם (לא בתגובה להודעת אורח) חייבות לעבור דרך WhatsApp
Content Templates שאושרו מראש ע"י Meta — טקסט חופשי (body=) נחסם מחוץ
לחלון שירות של 24 שעות מרגע שהאורח כתב לנו. לכן ההודעות האוטומטיות
(אישור/תזכורת/קוד כניסה/יציאה) נשלחות דרך content_sid + content_variables,
לא דרך body.
"""
import json
import logging
import re

from twilio.rest import Client
from app.config import settings

logger = logging.getLogger(__name__)

MAP_MEDIA_URL = "https://selfless-happiness-production.up.railway.app/static/map.jpeg"


def _to_e164(phone: str) -> str:
    """
    ממיר מספר טלפון ישראלי מקומי (054-1234567 / 0541234567 / 054 123 4567)
    לפורמט E.164 שTwilio דורש (+972541234567) — בלעדיו Twilio מחזיר
    "Invalid 'To' Phone Number" (Error 21211) ולא שולח כלום.

    אם המספר כבר בפורמט בינלאומי (+972... או 972...) — רק מנקה תווים
    (מקפים/רווחים/סוגריים), לא נוגע במבנה. לא נועד לתמוך במדינות אחרות
    מלבד ישראל (0XXXXXXXXX ← אורח ישראלי בהגדרה, זה המקור היחיד שראינו).
    """
    p = re.sub(r"[\s\-()]", "", phone or "").strip()
    if p.startswith("+972"):
        return p
    if p.startswith("972"):
        return "+" + p
    if p.startswith("0"):
        return "+972" + p[1:]
    # פורמט לא מזוהה — לא מנחשים, נותנים ל-Twilio להחזיר שגיאה ברורה
    # שתירשם ב-MessageLog כ-failed, כמו כל כשל שליחה אחר.
    logger.warning(f"Phone number in unrecognized format, sending as-is: {phone!r}")
    return p


def _whatsapp_address(to_phone: str) -> str:
    """בונה כתובת 'whatsapp:+972...' — מנרמל תמיד, גם אם כבר יש קידומת."""
    if to_phone.startswith("whatsapp:"):
        raw = to_phone[len("whatsapp:"):]
        return f"whatsapp:{_to_e164(raw)}"
    return f"whatsapp:{_to_e164(to_phone)}"


# Twilio Content Template SIDs — נוצרו ואושרו ב-Content Template Builder
# (Desert and Sea project, 9.7.2026). שינוי טקסט תבנית מאושרת מחייב תבנית
# חדשה + אישור מחדש מ-Meta — אי אפשר לערוך תבנית מאושרת במקום.
CONTENT_SIDS = {
    "confirmation": "HX60438a1a8fc85e4b4e2a345340518a22",
    "pre_arrival": "HX1e7b8909b9c0dd6a9d087abb02738dee",
    "entry_code": "HXe8412c1fc29af47dafe3f4c59b193582",  # door_access_instructions
    "checkout": "HX4a3baa4df38782b23d77ae46c5b67c1c",
}


def send_whatsapp_template(to_phone: str, message_type: str, variables: dict) -> str:
    """
    שולח הודעת WhatsApp דרך Content Template מאושר — זה מה שה-scheduler
    האוטומטי משתמש בו (מותר לשלוח יוזמת-עסק מחוץ לחלון שירות).
    variables: dict עם מפתחות כמחרוזת, למשל {"1": "רפי", "2": "מדבר"} —
    תואם למספרי {{1}} {{2}} בגוף התבנית ב-Twilio.
    Returns the Twilio message SID.
    """
    content_sid = CONTENT_SIDS.get(message_type)
    if not content_sid:
        raise ValueError(f"No content template configured for message_type={message_type}")

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    to = _whatsapp_address(to_phone)
    message = client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to,
        content_sid=content_sid,
        content_variables=json.dumps(variables),
    )
    return message.sid


def send_whatsapp(to_phone: str, body: str) -> str:
    """
    שליחת טקסט חופשי — פועל רק בתוך חלון שירות של 24 שעות (אחרי שהאורח
    כתב לנו קודם). לא לשימוש בהודעות שהעסק יוזם ראשון. שימושי להודעות
    ידניות/תגובות מהדשבורד — לא בשימוש ע"י ה-scheduler האוטומטי.
    Returns the Twilio message SID.
    """
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    to = _whatsapp_address(to_phone)
    message = client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to,
        body=body,
    )
    return message.sid


def send_whatsapp_with_map(to_phone: str, body: str) -> str:
    """
    שולח הודעת WhatsApp עם תמונת מפה + טקסט חופשי.
    הערה: כמו send_whatsapp — טקסט חופשי, פועל רק בתוך חלון שירות של 24
    שעות. לא בשימוש כרגע ע"י ה-scheduler האוטומטי (הודעת קוד הכניסה
    עברה ל-send_whatsapp_template, שאינו כולל מדיה בשלב זה).
    Returns the Twilio message SID.
    """
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    to = _whatsapp_address(to_phone)
    message = client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to,
        body=body,
        media_url=[MAP_MEDIA_URL],
    )
    return message.sid


# --- Legacy multi-language free-text templates -----------------------------
# נשמר לתאימות לאחור לזרימות ידניות/תגובה מהדשבורד (שם טקסט חופשי כן
# חוקי, כי הן בתוך חלון שירות). לא בשימוש ע"י ה-scheduler האוטומטי, שעבר
# ל-CONTENT_SIDS למעלה.
MESSAGE_TEMPLATES = {
    "pre_arrival": {
        "he": "שלום {name}, אנחנו מצפים לקבל אתכם ב-Desert and Sea! צ'ק-אין ב-{check_in}. לכל שאלה אנחנו כאן.",
        "en": "Hello {name}, we look forward to welcoming you at Desert and Sea! Check-in on {check_in}. Feel free to reach out.",
        "ar": "مرحباً {name}، نتطلع إلى استقبالكم في Desert and Sea! موعد الوصول {check_in}. نحن هنا لأي استفسار.",
        "ru": "Здравствуйте, {name}! Мы ждём вас в Desert and Sea! Заезд {check_in}. Будем рады помочь.",
    },
    "entry_code": {
        "he": "שלום {name}, קוד הכניסה שלכם הוא: *{code}*. הוא תקף מ-{check_in} עד {check_out}. נסיעה טובה!",
        "en": "Hello {name}, your entry code is: *{code}*. Valid from {check_in} to {check_out}. Safe travels!",
        "ar": "مرحباً {name}، رمز الدخول الخاص بكم هو: *{code}*. صالح من {check_in} إلى {check_out}.",
        "ru": "Здравствуйте, {name}! Ваш код входа: *{code}*. Действителен с {check_in} по {check_out}.",
    },
    "checkout": {
        "he": "שלום {name}, תודה שהתארחתם ב-Desert and Sea! נשמח לראותכם שוב. אנא השאירו ביקורת אם נהניתם. 🙏",
        "en": "Hello {name}, thank you for staying at Desert and Sea! We hope to see you again. Please leave a review if you enjoyed your stay. 🙏",
        "ar": "شكراً {name} على إقامتكم في Desert and Sea! نأمل في رؤيتكم مرة أخرى. 🙏",
        "ru": "Здравствуйте, {name}! Спасибо за пребывание в Desert and Sea! Будем рады видеть вас снова. 🙏",
    },
}


def build_message(template_key: str, language: str, **kwargs) -> str:
    """Build a message from a template for the given language, falling back to English."""
    templates = MESSAGE_TEMPLATES.get(template_key, {})
    template = templates.get(language, templates.get("en", ""))
    return template.format(**kwargs)
