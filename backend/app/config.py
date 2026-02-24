from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    minihotel_api_key: str
    minihotel_property_id: str

    ttlock_client_id: str
    ttlock_client_secret: str
    ttlock_access_token: str

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    secret_key: str
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
