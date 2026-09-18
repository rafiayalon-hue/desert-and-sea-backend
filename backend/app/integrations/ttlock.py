"""
TTLock integration — Desert and Sea.

Two locks, each behind a gateway (remote programming enabled).
Auth: OAuth2 password grant (username = email, password = MD5).
Token auto-refreshed on expiry (~90 days).

Public API expected by the rest of the app:
  LOCK_IDS                              dict: room -> lockId
  assign_passcode_to_booking(booking, db, passcode=None) -> str   (the code)
  remove_passcode_after_checkout(booking, db) -> bool
  list_passcodes(lock_id) -> list[dict]
  delete_passcode_by_id(lock_id, keyboard_pwd_id) -> bool
  get_lock_status(lock_id) -> dict
"""
import hashlib
import logging
import random
import time as _time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://euapi.ttlock.com/oauth2/token"
BASE_URL = "https://euapi.ttlock.com/v3"

# room key -> lockId   (מדבר / ים ; קוד בעלים 4708# לא נוגעים בו)
LOCK_IDS: dict[str, int] = {
    "desert": 18201474,   # מדבר ('Sesert')
    "sea":    18201274,   # ים ('Sea')
}


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------
_token_cache: dict = {"access_token": None, "expires_at": 0}


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


async def _fetch_token() -> str:
    payload = {
        "clientId":     settings.ttlock_client_id,
        "clientSecret": settings.ttlock_client_secret,
        "username":     settings.ttlock_username,
        "password":     _md5(settings.ttlock_password),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(AUTH_URL, data=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TTLock auth failed: {data}")
    # expires_in is in seconds; refresh 1 day early
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = _time.time() + int(data.get("expires_in", 7776000)) - 86400
    logger.info("TTLock: token acquired")
    return data["access_token"]


async def _get_token() -> str:
    if _token_cache["access_token"] and _time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]
    return await _fetch_token()


def _check(data: dict) -> dict:
    """TTLock returns errcode 0 on success; anything else is an error."""
    if isinstance(data, dict) and data.get("errcode", 0) not in (0, None):
        raise RuntimeError(f"TTLock error {data.get('errcode')}: {data.get('errmsg')}")
    return data


# ---------------------------------------------------------------------------
# Low-level passcode operations (per lock)
# ---------------------------------------------------------------------------
async def _add_passcode(lock_id: int, passcode: str, name: str,
                        start_ms: int, end_ms: int) -> int:
    """Create a dictated (custom) period passcode via gateway. Returns keyboardPwdId."""
    token = await _get_token()
    payload = {
        "clientId":     settings.ttlock_client_id,
        "accessToken":  token,
        "lockId":       lock_id,
        "keyboardPwd":  passcode,
        "keyboardPwdName": name,
        "startDate":    start_ms,
        "endDate":      end_ms,
        "addType":      2,      # 2 = via gateway
        "date":         int(_time.time() * 1000),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/keyboardPwd/add", data=payload, timeout=15)
        r.raise_for_status()
        data = _check(r.json())
    return data.get("keyboardPwdId")


async def list_passcodes(lock_id: int) -> list[dict]:
    """All keyboard passcodes on a lock."""
    token = await _get_token()
    params = {
        "clientId":    settings.ttlock_client_id,
        "accessToken": token,
        "lockId":      lock_id,
        "pageNo":      1,
        "pageSize":    100,
        "date":        int(_time.time() * 1000),
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/lock/listKeyboardPwd", params=params, timeout=15)
        r.raise_for_status()
        data = _check(r.json())
    return data.get("list", [])


async def delete_passcode_by_id(lock_id: int, keyboard_pwd_id: int) -> bool:
    """Delete a passcode from a lock by its keyboardPwdId (via gateway)."""
    token = await _get_token()
    payload = {
        "clientId":       settings.ttlock_client_id,
        "accessToken":    token,
        "lockId":         lock_id,
        "keyboardPwdId":  keyboard_pwd_id,
        "deleteType":     2,     # 2 = via gateway
        "date":           int(_time.time() * 1000),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/keyboardPwd/delete", data=payload, timeout=15)
        r.raise_for_status()
        _check(r.json())
    return True


async def get_lock_status(lock_id: int) -> dict:
    """Lock detail: battery (electricQuantity), name, gateway presence."""
    token = await _get_token()
    params = {
        "clientId":    settings.ttlock_client_id,
        "accessToken": token,
        "lockId":      lock_id,
        "date":        int(_time.time() * 1000),
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/lock/detail", params=params, timeout=15)
        r.raise_for_status()
        data = _check(r.json())
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_lock_ids(room_name: str) -> list[int]:
    """
    Map a booking.room_name to one or more lockIds.
    Handles the 'Sesert' typo, English names, Hebrew, and combined 'des_sea'.
    """
    n = (room_name or "").strip().lower().replace(" ", "")
    if "des_sea" in n:
        return [LOCK_IDS["desert"], LOCK_IDS["sea"]]
    if "sesert" in n or "desert" in n or "מדבר" in (room_name or ""):
        return [LOCK_IDS["desert"]]
    if "sea" in n or "ים" in (room_name or ""):
        return [LOCK_IDS["sea"]]
    return []


def _gen_code() -> str:
    """4-digit random code (avoids owner code 4708)."""
    while True:
        code = f"{random.randint(1000, 9999)}"
        if code != "4708":
            return code


def _to_ms(d) -> int:
    """date/datetime -> epoch ms. check_in at 14:00, check_out at 12:00."""
    from datetime import datetime, time
    if hasattr(d, "hour"):
        dt = d
    else:
        dt = datetime.combine(d, time(0, 0))
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# High-level operations (called by routes / scheduler)
# ---------------------------------------------------------------------------
async def assign_passcode_to_booking(booking, db: AsyncSession,
                                     passcode: str | None = None) -> str:
    """
    Create a period passcode on the relevant lock(s) for a booking,
    store entry_code + ttlock_pwd_ids on the booking, commit, return the code.
    """
    from datetime import datetime, time

    lock_ids = _resolve_lock_ids(booking.room_name)
    if not lock_ids:
        logger.error(f"Booking {booking.id}: cannot resolve lock for room '{booking.room_name}'")
        return ""

    code = passcode or booking.entry_code or _gen_code()

    # window: check_in 14:00 → check_out 12:00
    start_dt = datetime.combine(booking.check_in, time(14, 0))
    end_dt   = datetime.combine(booking.check_out, time(12, 0))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms   = int(end_dt.timestamp() * 1000)

    name = f"{booking.guest_name or 'Guest'} #{booking.id}"

    pwd_ids = []
    for lock_id in lock_ids:
        try:
            pid = await _add_passcode(lock_id, code, name, start_ms, end_ms)
            if pid:
                pwd_ids.append(f"{lock_id}:{pid}")
        except Exception as e:
            logger.error(f"Booking {booking.id}: TTLock add failed on lock {lock_id}: {e}")
            raise

    booking.entry_code = code
    booking.ttlock_pwd_ids = ",".join(pwd_ids)
    db.add(booking)
    await db.commit()
    logger.info(f"Booking {booking.id}: passcode {code} set on {pwd_ids}")
    return code


async def remove_passcode_after_checkout(booking, db: AsyncSession) -> bool:
    """Delete the booking's passcode(s) from the lock(s) and clear DB fields."""
    if not booking.ttlock_pwd_ids:
        return False

    ok = True
    for entry in booking.ttlock_pwd_ids.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        lock_id_s, pwd_id_s = entry.split(":", 1)
        try:
            await delete_passcode_by_id(int(lock_id_s), int(pwd_id_s))
        except Exception as e:
            logger.error(f"Booking {booking.id}: TTLock delete failed for {entry}: {e}")
            ok = False

    booking.ttlock_pwd_ids = None
    booking.entry_code = None
    db.add(booking)
    await db.commit()
    return ok


async def update_passcode_window(booking, db: AsyncSession) -> bool:
    """
    Update the validity window (start/end) of a booking's existing passcode(s)
    on the lock(s), after check-in/checkout times were edited. Uses the same
    period the booking now implies: check_in 14:00 → check_out 12:00, unless
    booking.checkin_time / checkout_time override the hour. No-op (returns
    False) if the booking has no passcode yet.
    """
    from datetime import datetime, time

    if not booking.ttlock_pwd_ids:
        return False

    def _hhmm(val, default_h, default_m):
        try:
            h, m = str(val).strip().split(":")
            return time(int(h), int(m))
        except Exception:
            return time(default_h, default_m)

    ci_time = _hhmm(getattr(booking, "checkin_time", None), 14, 0)
    co_time = _hhmm(getattr(booking, "checkout_time", None), 12, 0)
    start_ms = int(datetime.combine(booking.check_in, ci_time).timestamp() * 1000)
    end_ms = int(datetime.combine(booking.check_out, co_time).timestamp() * 1000)

    token = await _get_token()
    ok = True
    for entry in booking.ttlock_pwd_ids.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        lock_id_s, pwd_id_s = entry.split(":", 1)
        payload = {
            "clientId":      settings.ttlock_client_id,
            "accessToken":   token,
            "lockId":        int(lock_id_s),
            "keyboardPwdId": int(pwd_id_s),
            "startDate":     start_ms,
            "endDate":       end_ms,
            "changeType":    2,   # 2 = via gateway
            "date":          int(_time.time() * 1000),
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{BASE_URL}/keyboardPwd/changePeriod", data=payload, timeout=15)
                r.raise_for_status()
                _check(r.json())
        except Exception as e:
            logger.error(f"Booking {booking.id}: TTLock changePeriod failed for {entry}: {e}")
            ok = False
    return ok
