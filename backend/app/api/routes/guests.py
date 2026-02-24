from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Guest

router = APIRouter()


@router.get("/")
async def list_guests(
    returning_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(Guest).order_by(Guest.name)
    if returning_only:
        query = query.where(Guest.is_returning == True)
    result = await db.scalars(query)
    return result.all()


@router.get("/{guest_id}")
async def get_guest(guest_id: int, db: AsyncSession = Depends(get_db)):
    guest = await db.get(Guest, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="אורח לא נמצא")
    return guest


@router.patch("/{guest_id}/notes")
async def update_notes(
    guest_id: int, notes: str, db: AsyncSession = Depends(get_db)
):
    guest = await db.get(Guest, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="אורח לא נמצא")
    guest.notes = notes
    await db.commit()
    return guest
