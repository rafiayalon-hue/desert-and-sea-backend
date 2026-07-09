import secrets
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CheckinToken(Base):
    """
    טוקן ציבורי לעמוד 'פרטי הכניסה שלי' באתר הציבורי (WordPress).
    כל הזמנה מקבלת טוקן אחד, שתקף עד יום ה-checkout.
    """
    __tablename__ = "checkin_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking")

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(24)
