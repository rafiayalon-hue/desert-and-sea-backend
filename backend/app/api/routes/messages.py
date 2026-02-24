from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.integrations.whatsapp import build_message, send_whatsapp
from app.models import Booking, Guest, MessageLog

router = APIRouter()


class SendMessageRequest(BaseModel):
    phone: str
    body: str
    booking_id: int | None = None
    guest_id: int | None = None
    message_type: str = "manual"


class CampaignRequest(BaseModel):
    template_key: str
    guest_ids: list[int]
    extra: dict = {}


@router.get("/")
async def list_messages(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(MessageLog).order_by(MessageLog.created_at.desc()))
    return result.all()


@router.post("/send")
async def send_message(req: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    try:
        sid = send_whatsapp(req.phone, req.body)
        status = "sent"
    except Exception as e:
        sid = None
        status = "failed"

    log = MessageLog(
        booking_id=req.booking_id,
        guest_id=req.guest_id,
        phone=req.phone,
        message_type=req.message_type,
        body=req.body,
        status=status,
        twilio_sid=sid,
    )
    db.add(log)
    await db.commit()
    return {"status": status, "twilio_sid": sid}


@router.post("/campaign")
async def send_campaign(req: CampaignRequest, db: AsyncSession = Depends(get_db)):
    """Send a templated message to a list of returning guests."""
    results = []
    for guest_id in req.guest_ids:
        guest = await db.get(Guest, guest_id)
        if not guest:
            continue
        body = build_message(req.template_key, guest.language, name=guest.name, **req.extra)
        try:
            sid = send_whatsapp(guest.phone, body)
            status = "sent"
        except Exception:
            sid = None
            status = "failed"
        log = MessageLog(
            guest_id=guest_id,
            phone=guest.phone,
            message_type="campaign",
            body=body,
            status=status,
            twilio_sid=sid,
        )
        db.add(log)
        results.append({"guest_id": guest_id, "status": status})
    await db.commit()
    return {"sent": len(results), "results": results}
