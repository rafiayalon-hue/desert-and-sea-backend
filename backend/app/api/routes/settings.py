from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.business_settings import BusinessSettings

router = APIRouter()


class SettingsUpdate(BaseModel):
    business_name_he: str | None = None
    business_name_en: str | None = None
    business_type: str | None = None
    company_id: str | None = None
    address: str | None = None
    website: str | None = None
    phone_business: str | None = None
    email_business: str | None = None
    owner1_name_he: str | None = None
    owner1_name_en: str | None = None
    owner1_phone: str | None = None
    owner1_email: str | None = None
    owner1_vat_id: str | None = None
    owner2_name_he: str | None = None
    owner2_name_en: str | None = None
    owner2_phone: str | None = None
    owner2_email: str | None = None
    owner2_vat_id: str | None = None
    default_checkin_time: str | None = None
    default_checkout_time: str | None = None


async def _get_or_create(db: AsyncSession) -> BusinessSettings:
    result = await db.execute(select(BusinessSettings).where(BusinessSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = BusinessSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("/")
async def get_settings(db: AsyncSession = Depends(get_db)):
    settings = await _get_or_create(db)
    return settings


@router.patch("/")
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    settings = await _get_or_create(db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    await db.commit()
    await db.refresh(settings)
    return settings
