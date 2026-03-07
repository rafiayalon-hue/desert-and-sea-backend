from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    database_url: str
    
    @field_validator("database_url")
    @classmethod
    def fix_db_url(cls, v):
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    
    redis_url: str = "redis://localhost:6379/0"
    minihotel_api_key: str
    minihotel_property_id: str
    ttlock_client_id: Optional[str] = None
    ttlock_client_secret: Optional[str] = None
    ttlock_access_token: Optional[str] = None
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    secret_key: str
    debug: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
