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
    MH_USER: str
    MH_PASS: str  
    MINIHOTEL_HOTEL_ID: str
    
    TTLOCK_CLIENT_ID:     str = "d9293b3d0ec247dcabe3b3dc1599e0a8"
    TTLOCK_CLIENT_SECRET: str = ""
    TTLOCK_USERNAME:      str = "rafiayalon@gmail.com"
    TTLOCK_PASSWORD:      str = ""
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    secret_key: str
    debug: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
