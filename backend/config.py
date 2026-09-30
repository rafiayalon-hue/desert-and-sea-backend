from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    # ── Core ────────────────────────────────────────────────
    database_url: str = ""
    secret_key: str = "desert-and-sea-secret"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"
    # ── MiniHotel (names the existing code reads — UPPERCASE) ──
    MH_USER: str = "desertsea"
    MH_PASS: str = "desert@@003"   # TODO: להעביר למשתנה MH_PASS ב-Railway ולמחוק מכאן (הסיסמה חשופה ב-GitHub)
    MINIHOTEL_HOTEL_ID: str = "desert89"
    # lowercase / extra MiniHotel fields (optional, tolerated)
    minihotel_api_key: str = ""
    minihotel_property_id: str = ""
    minihotel_username: str = ""
    minihotel_password: str = ""
    minihotel_use_sandbox: bool = False
    mh_base: str = "https://api2.minihotel.cloud"
    # ── MiniHotel Webhook (Basic Auth — MiniHotel authenticates TO us) ──
    minihotel_webhook_user: str = ""
    minihotel_webhook_password: str = ""
    # ── TTLock ──────────────────────────────────────────────
    ttlock_client_id: str = ""
    ttlock_client_secret: str = ""
    ttlock_username: str = ""
    ttlock_password: str = ""
    ttlock_access_token: str = ""   # optional legacy; new flow generates its own
    # ── Twilio ──────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    # NEW (17.7.26): מספר Twilio אמריקאי קיים (SMS), לשליחת התראת SMS
    # לרפי/אבישג כשמגיעה הודעת WhatsApp נכנסת — לא כפוף ל-A2P 10DLC כי
    # היעד הוא ישראל, לא ארה"ב (A2P חל רק על הודעות שהיעד שלהן בארה"ב).
    twilio_sms_from: str = ""
    # ── SMS ישראלי (019SMS) — NEW (30.9.26): גיבוי כש-WhatsApp נכשל ──
    sms_019_username: str = ""
    sms_019_token: str = ""
    sms_sender: str = "DesertSea"     # עד 11 תווים, אנגלית/ספרות
    sms_enabled: bool = True          # מתג כללי; בפועל פעיל רק אם יש טוקן
    # קישור לעמוד "פרטי הכניסה שלי" באתר, עם {token} במקום הטוקן.
    # ריק = ה-SMS יישלח בלי קישור (רק עם הקוד).
    checkin_page_url: str = ""
    class Config:
        env_file = ".env"
        case_sensitive = False   # TTLOCK_CLIENT_ID → ttlock_client_id
        extra = "ignore"         # don't crash on unknown Railway vars
settings = Settings()
