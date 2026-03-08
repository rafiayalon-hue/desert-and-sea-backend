from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    minihotel_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"), nullable=True)

    # פרטי אורח
    guest_name: Mapped[str] = mapped_column(String(200))
    guest_phone: Mapped[str] = mapped_column(String(20), default="")
    guest_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)

    # פרטי שהייה
    room_name: Mapped[str] = mapped_column(String(100))
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2))
    balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # מצב
    status: Mapped[str] = mapped_column(String(50), default="confirmed")
    entry_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guest = relationship("Guest", backref="bookings")
