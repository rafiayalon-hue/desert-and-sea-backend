"""
APScheduler jobs that run automatically:
- Sync bookings from MiniHotel every hour
- Send pre-arrival WhatsApp messages (24h before check-in)
- Send entry code messages (day of check-in, morning)
- Send checkout messages (day of check-out, morning)
"""
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.integrations.minihotel import minihotel_client
from app.integrations.ttlock import ttlock_client
from app.integrations.whatsapp import build_message, send_whatsapp
from app.models import Booking, Guest, MessageLog

scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")


@scheduler.scheduled_job("interval", hours=1, id="sync_bookings")
async def sync_bookings_job():
    """Pull upcoming bookings from MiniHotel and upsert into local DB."""
    today = date.today()
    raw = await minihotel_client.get_bookings(
        str(today), str(today + timedelta(days=60))
    )
    async with AsyncSessionLocal() as session:
        for item in raw:
            existing = await session.scalar(
                select(Booking).where(Booking.minihotel_id == str(item["id"]))
            )
            if not existing:
                booking = Booking(
                    minihotel_id=str(item["id"]),
                    guest_name=item.get("guest_name", ""),
                    guest_phone=item.get("guest_phone", ""),
                    room_name=item.get("room", ""),
                    check_in=item.get("check_in"),
                    check_out=item.get("check_out"),
                    total_price=item.get("total", 0),
                    status=item.get("status", "confirmed"),
                )
                session.add(booking)
        await session.commit()


@scheduler.scheduled_job("cron", hour=9, minute=0, id="send_scheduled_messages")
async def send_scheduled_messages_job():
    """Send pre-arrival, entry code, and checkout messages each morning."""
    today = date.today()
    tomorrow = today + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        bookings = (await session.scalars(select(Booking))).all()
        for booking in bookings:
            guest = await session.get(Guest, booking.guest_id) if booking.guest_id else None
            language = guest.language if guest else "he"

            # Pre-arrival: 1 day before check-in
            if booking.check_in == tomorrow:
                await _send_and_log(
                    session, booking, "pre_arrival", language,
                    name=booking.guest_name, check_in=str(booking.check_in),
                )

            # Entry code: day of check-in
            if booking.check_in == today and booking.entry_code:
                await _send_and_log(
                    session, booking, "entry_code", language,
                    name=booking.guest_name, code=booking.entry_code,
                    check_in=str(booking.check_in), check_out=str(booking.check_out),
                )

            # Checkout: day of check-out
            if booking.check_out == today:
                await _send_and_log(
                    session, booking, "checkout", language,
                    name=booking.guest_name,
                )

        await session.commit()


async def _send_and_log(session, booking: Booking, msg_type: str, language: str, **kwargs):
    body = build_message(msg_type, language, **kwargs)
    try:
        sid = send_whatsapp(booking.guest_phone, body)
        status = "sent"
    except Exception:
        sid = None
        status = "failed"

    log = MessageLog(
        booking_id=booking.id,
        phone=booking.guest_phone,
        message_type=msg_type,
        body=body,
        status=status,
        twilio_sid=sid,
    )
    session.add(log)
