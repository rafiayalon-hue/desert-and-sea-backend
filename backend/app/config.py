from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Core ────────────────────────────────────────────────
    database_url: str
    secret_key: str = "desert-and-sea-secret"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # ── MiniHotel ───────────────────────────────────────────
    minihotel_api_key: str = ""
    minihotel_property_id: str = ""
    minihotel_hotel_id: str = ""
    minihotel_username: str = ""
    minihotel_password: str = ""
    minihotel_use_sandbox: bool = False
    mh_user: str = ""
    mh_pass: str = ""
    mh_base: str = "https://api2.minihotel.cloud"

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

    class Config:
        env_file = ".env"
        case_sensitive = False   # TTLOCK_CLIENT_ID → ttlock_client_id
        extra = "ignore"         # don't crash on unknown Railway vars


settings = Settings()
