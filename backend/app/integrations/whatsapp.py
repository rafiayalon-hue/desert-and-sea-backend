"""
Twilio WhatsApp integration for sending messages to guests.
"""
from twilio.rest import Client

from app.config import settings

_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

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


def send_whatsapp(to_phone: str, body: str) -> str:
    """Send a WhatsApp message. Returns the Twilio message SID."""
    to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
    message = _client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to,
        body=body,
    )
    return message.sid


def build_message(template_key: str, language: str, **kwargs) -> str:
    """Build a message from a template for the given language, falling back to English."""
    templates = MESSAGE_TEMPLATES.get(template_key, {})
    template = templates.get(language, templates.get("en", ""))
    return template.format(**kwargs)
