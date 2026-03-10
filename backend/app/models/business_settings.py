from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BusinessSettings(Base):
    __tablename__ = "business_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # פרטי העסק
    business_name_he: Mapped[str | None] = mapped_column(String(200), nullable=True, default="מדבר וים")
    business_name_en: Mapped[str | None] = mapped_column(String(200), nullable=True, default="Desert and Sea")
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True, default="שותפות רשומה")
    company_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default="558487823")
    address: Mapped[str | None] = mapped_column(String(300), nullable=True, default="קיבוץ מעלה צרויה 2, עין גדי, ישראל")
    website: Mapped[str | None] = mapped_column(String(200), nullable=True, default="https://desert-sea.co.il/")
    phone_business: Mapped[str | None] = mapped_column(String(20), nullable=True, default="052-3730377")
    email_business: Mapped[str | None] = mapped_column(String(200), nullable=True, default="rafi@desert-sea.co.il")

    # רפי
    owner1_name_he: Mapped[str | None] = mapped_column(String(100), nullable=True, default="רפי איילון")
    owner1_name_en: Mapped[str | None] = mapped_column(String(100), nullable=True, default="Rafi Ayalon")
    owner1_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, default="058-4222666")
    owner1_email: Mapped[str | None] = mapped_column(String(200), nullable=True, default="rafiayalon@gmail.com")
    owner1_vat_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default="022058580")

    # אבישג
    owner2_name_he: Mapped[str | None] = mapped_column(String(100), nullable=True, default="אבישג איילון")
    owner2_name_en: Mapped[str | None] = mapped_column(String(100), nullable=True, default="Avishag Ayalon")
    owner2_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, default="052-3960773")
    owner2_email: Mapped[str | None] = mapped_column(String(200), nullable=True, default="avishaga@ein-gedi.co.il")
    owner2_vat_id: Mapped[str | None] = mapped_column(String(50), nullable=True, default="032081937")

    # שעות ברירת מחדל
    default_checkin_time: Mapped[str | None] = mapped_column(String(10), nullable=True, default="14:00")
    default_checkout_time: Mapped[str | None] = mapped_column(String(10), nullable=True, default="14:00")

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
