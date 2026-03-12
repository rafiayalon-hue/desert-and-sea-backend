"""
TTLock API integration for Desert and Sea.

Handles:
- OAuth2 token management (auto-refresh)
- Create passcode for guest (with validity period)
- Delete passcode after checkout
- List existing passcodes per lock
- Receive unlock callbacks

Lock IDs:
  Desert (מדבר): 18201474
  Sea    (ים):   18201274

Owner passcode 4708# is NEVER touched by this module.
"""
import hashlib
import logging
import time
from datetime import datetime, date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Booking

logger = logging.getLogger(__name__)

BASE_URL = "https://euapi.ttlock.com"

LOCK_IDS = {
    "desert": 18201474,
    "sea":    18201274,
}

# קוד קבוע של הבעלים — לא נוגעים בו לעולם
OWNER_CODE = "4708"


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

_token_cache: dict = {}


async def _get_token() -> str:
    """
    Return a valid access_token.
    Uses cached token if still valid (expires_in - 60s buffer).
    """
    now = time.time()
    if _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    md5_pass = hashlib.md5(settings.TTLOCK_PASSWORD.encode()).hexdigest()

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/oauth2/token", data={
            "client_id":     settings.TTLOCK_CLIENT_ID,
            "client_secret": settings.TTLOCK_CLIENT_SECRET,
            "grant_type":    "password",
            "username":      settings.TTLOCK_USERNAME,
            "password":      md5_pass,
        })
        r.raise_for_status()
        data = r.json()

    if "access_token" not in data:
        raise RuntimeError(f"TTLock token error: {data}")

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"]   = now + data.get("expires_in", 7776000)
    logger.info("TTLock: new access_token acquired")
    return _token_cache["access_token"]


def _ts() -> int:
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


def _to_ms(d: date, hour: int = 0, minute: int = 0) -> int:
    """Date → milliseconds timestamp at given time."""
    return int(datetime(d.year, d.month, d.day, hour, minute).timestamp() * 1000)


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------

def _lock_id_for_booking(booking: Booking) -> int | None:
    """Return lockId based on booking room_name."""
    room = (booking.room_name or "").lower()
    if "sesert" in room or "desert" in room:
        return LOCK_IDS["desert"]
    if "sea" in room:
        return LOCK_IDS["sea"]
    # שני חדרים — מחזיר desert כברירת מחדל (יטופל נפרד)
    return None


def _both_locks(booking: Booking) -> list[int]:
    """Return lock IDs for booking — both if combined room."""
    room = (booking.room_name or "").lower()
    if ("sesert" in room or "desert" in room) and "sea" in room:
        return [LOCK_IDS["desert"], LOCK_IDS["sea"]]
    if "sesert" in room or "desert" in room:
        return [LOCK_IDS["desert"]]
    if "sea" in room:
        return [LOCK_IDS["sea"]]
    return []


# ---------------------------------------------------------------------------
# Passcode operations
# ---------------------------------------------------------------------------

async def create_guest_passcode(
    booking: Booking,
    passcode: str | None = None,
) -> dict:
    """
    Create a time-limited passcode for the guest.

    Args:
        booking:  Booking object with check_in, check_out, room_name
        passcode: 4-9 digit code. If None, auto-generates from booking id.

    Returns:
        {"desert": keyboardPwdId, "sea": keyboardPwdId} for rooms in booking.
    """
    if passcode is None:
        # גנרציה אוטומטית: 4 ספרות אחרונות של booking_id + check_in day
        base = str(booking.id).zfill(4)[-4:]
        passcode = base

    # וודא שהקוד לא זהה לקוד הבעלים
    if passcode == OWNER_CODE:
        passcode = str((int(passcode) + 1) % 10000).zfill(4)

    token = await _get_token()
    lock_ids = _both_locks(booking)

    if not lock_ids:
        raise ValueError(f"No lock found for room: {booking.room_name}")

    # תוקף: מחצות יום הכניסה עד חצות יום אחרי יציאה
    start_ms = _to_ms(booking.check_in, 0, 0)
    end_ms   = _to_ms(booking.check_out, 23, 59)

    results = {}
    async with httpx.AsyncClient() as client:
        for lock_id in lock_ids:
            room_key = "desert" if lock_id == LOCK_IDS["desert"] else "sea"

            payload = {
                "clientId":        settings.TTLOCK_CLIENT_ID,
                "accessToken":     token,
                "lockId":          lock_id,
                "keyboardPwdType": 2,           # custom passcode
                "keyboardPwd":     passcode,
                "startDate":       start_ms,
                "endDate":         end_ms,
                "addType":         2,            # Gateway add
                "date":            _ts(),
            }
            r = await client.post(f"{BASE_URL}/v3/keyboardPwd/add", data=payload)
            r.raise_for_status()
            data = r.json()

            if data.get("errmsg") == "SUCCESS" or "keyboardPwdId" in data:
                results[room_key] = {
                    "keyboardPwdId": data.get("keyboardPwdId"),
                    "passcode":      passcode,
                    "lockId":        lock_id,
                }
                logger.info(f"TTLock: created passcode {passcode} for {room_key} lock {lock_id}, booking {booking.id}")
            else:
                logger.error(f"TTLock: create failed for {room_key}: {data}")
                results[room_key] = {"error": data}

    return results


async def delete_guest_passcode(
    lock_id: int,
    keyboard_pwd_id: int,
) -> bool:
    """Delete a passcode by its keyboardPwdId."""
    token = await _get_token()

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/v3/keyboardPwd/delete", data={
            "clientId":        settings.TTLOCK_CLIENT_ID,
            "accessToken":     token,
            "lockId":          lock_id,
            "keyboardPwdId":   keyboard_pwd_id,
            "deleteType":      2,
            "date":            _ts(),
        })
        r.raise_for_status()
        data = r.json()

    success = data.get("errmsg") == "SUCCESS"
    if success:
        logger.info(f"TTLock: deleted passcode {keyboard_pwd_id} from lock {lock_id}")
    else:
        logger.error(f"TTLock: delete failed: {data}")
    return success


async def list_passcodes(lock_id: int) -> list[dict]:
    """List all passcodes for a lock."""
    token = await _get_token()

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/v3/lock/listKeyboardPwd", params={
            "clientId":    settings.TTLOCK_CLIENT_ID,
            "accessToken": token,
            "lockId":      lock_id,
            "pageNo":      1,
            "pageSize":    50,
            "date":        _ts(),
        })
        r.raise_for_status()
        data = r.json()

    return data.get("list", [])


async def get_lock_status(lock_id: int) -> dict:
    """Get current lock status (battery, online, etc.)."""
    token = await _get_token()

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/v3/lock/detail", params={
            "clientId":    settings.TTLOCK_CLIENT_ID,
            "accessToken": token,
            "lockId":      lock_id,
            "date":        _ts(),
        })
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# High-level: manage passcode for booking
# ---------------------------------------------------------------------------

async def assign_passcode_to_booking(
    booking: Booking,
    db: AsyncSession,
    passcode: str | None = None,
) -> str:
    """
    Create passcode, save to booking.entry_code, save keyboardPwdIds to DB.
    Returns the passcode string.

    For returning guests: if booking.entry_code already set, reuse it.
    """
    # אורח חוזר עם קוד קיים
    if booking.is_returning_guest and booking.entry_code and booking.entry_code != "יישלח בנפרד":
        logger.info(f"Booking {booking.id}: returning guest, reusing code {booking.entry_code}")
        # עדיין צריך ליצור את הקוד מחדש ב-TTLock עם תוקף חדש
        passcode = booking.entry_code

    results = await create_guest_passcode(booking, passcode)

    # שמור את הקוד הראשון שהצליח
    actual_code = None
    pwd_ids = {}
    for room_key, val in results.items():
        if "passcode" in val:
            actual_code = val["passcode"]
        if "keyboardPwdId" in val:
            pwd_ids[room_key] = val["keyboardPwdId"]

    if actual_code:
        booking.entry_code = actual_code
        # שמור keyboardPwdIds ב-notes_internal (JSON) לשימוש בעת מחיקה
        import json
        booking.ttlock_pwd_ids = json.dumps(pwd_ids)
        await db.commit()
        logger.info(f"Booking {booking.id}: entry_code={actual_code}, pwd_ids={pwd_ids}")

    return actual_code or ""


async def remove_passcode_after_checkout(booking: Booking, db: AsyncSession) -> bool:
    """Delete passcode from TTLock after checkout. Skip owner code."""
    import json

    if not booking.ttlock_pwd_ids:
        logger.info(f"Booking {booking.id}: no ttlock_pwd_ids, skipping delete")
        return False

    # לא מוחקים את קוד הבעלים
    if booking.entry_code == OWNER_CODE:
        logger.info(f"Booking {booking.id}: owner code, skipping delete")
        return False

    try:
        pwd_ids = json.loads(booking.ttlock_pwd_ids)
    except Exception:
        return False

    success = True
    for room_key, pwd_id in pwd_ids.items():
        lock_id = LOCK_IDS.get(room_key)
        if lock_id and pwd_id:
            ok = await delete_guest_passcode(lock_id, pwd_id)
            if not ok:
                success = False

    if success:
        booking.entry_code = None
        booking.ttlock_pwd_ids = None
        await db.commit()

    return success
