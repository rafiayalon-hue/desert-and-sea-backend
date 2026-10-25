"""
NEW (25.10.26) — מצב תפעולי להזמנה: הכנת הצימר להגעה + תשלום/קבלה ביציאה.

טבלה נפרדת (ולא עמודות ב-bookings) כדי לא לגעת במודל ההזמנה ובמיגרציות.
בכוונה אין ForeignKey ל-bookings.id: מחיקת הזמנה (DELETE /api/bookings/{id})
חסומה אם יש טבלה שמצביעה עליה (ראו ForeignKeyViolation על message_logs).
שורה יתומה כאן לא מזיקה.

הטבלה נוצרת אוטומטית ע"י Base.metadata.create_all בעליית השרת, כל עוד המודל
מיובא (ops.py מייבא אותו, וה-main מייבא את ops).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BookingOps(Base):
    __tablename__ = "booking_ops"

    booking_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # הכנת הצימר להגעה: dirty / partial / clean
    prep_status: Mapped[str] = mapped_column(String(20), default="dirty")
    # JSON: {"milk": true, "notes": false, ...}
    checklist: Mapped[str] = mapped_column(Text, default="{}")
    # יין/תשורה (יום הולדת, לקוח חוזר...) — רק כשמסומן, הפריט נכנס לרשימה
    gift_needed: Mapped[bool] = mapped_column(Boolean, default=False)

    # תשלום: unpaid / link_sent / paid
    pay_status: Mapped[str] = mapped_column(String(20), default="unpaid")
    # רפי הוציא חשבונית מס/קבלה
    receipt_issued: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
