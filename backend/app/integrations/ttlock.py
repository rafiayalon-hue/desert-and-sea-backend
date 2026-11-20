"""
TTLock integration — Desert and Sea.

Two locks, each behind a gateway (remote programming enabled).
Auth: OAuth2 password grant (username = email, password = MD5).
Token auto-refreshed on expiry (~90 days).

Public API expected by the rest of the app:
  LOCK_IDS                              dict: room -> lockId
  assign_passcode_to_booking(booking, db, passcode=None) -> str   (the code)
  remove_passcode_after_checkout(booking, db) -> bool
  update_passcode_window(booking, db) -> bool
  list_passcodes(lock_id) -> list[dict]
  delete_passcode_by_id(lock_id, keyboard_pwd_id) -> bool
  get_lock_status(lock_id) -> dict
  query_open_state(lock_id) -> dict        (NEW 4.10.26 — זמינות חיה)
  list_lock_records(lock_id, start, end)   (NEW 4.10.26 — לוג פתיחות)

תיקון (2.10.26) — אזור זמן:
  השרת ב-Railway רץ ב-UTC. datetime.combine(...).timestamp() על תאריך "נאיבי"
  פירש 14:00 כ-14:00 UTC → במנעול (שעון ישראל) הופיע 17:00. עכשיו כל חלון
  זמן נבנה עם Asia/Jerusalem — כולל מעבר אוטומטי לשעון חורף.
NEW (20.11.26) — אורח חוזר = אותו קוד:
  הזמנה של אורח חוזר (אותו טלפון, שהייה קודמת שהסתיימה) מקבלת כקוד כניסה את
  4 הספרות האחרונות של הטלפון — בשני הצימרים. אורח חדש ממשיך לקבל קוד אקראי.
  אם הקוד תפוס (הזמנה חופפת באותו מנעול / קוד זהה קיים במנעול / קוד בעלים או
  מנקה) — נוצר קוד אקראי ורפי ואבישג מקבלים התראה.
תיקון (2.10.26) — שעות מההזמנה:
  יצירת קוד התעלמה מ-checkin_time / checkout_time שבהזמנה (תמיד 14:00→12:00).
  עכשיו גם היצירה וגם העדכון משתמשים באותו חלון (_booking_window).
"""
import hashlib
import logging
import os
import random
import time as _time
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://euapi.ttlock.com/oauth2/token"
BASE_URL = "https://euapi.ttlock.com/v3"

TZ = ZoneInfo("Asia/Jerusalem")

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


async def query_open_state(lock_id: int) -> dict:
    """NEW (4.10.26): בדיקה חיה דרך הגייטווי — האם המנעול עונה עכשיו.
    lock/detail מחזיר נתון שמור בענן גם כשהמנעול מושבת (מצב שבת / בלי חשמל),
    לכן לזמינות צריך שאילתה שמעירה את המנעול.
    מחזיר {"reachable": bool, "state": 0 נעול / 1 פתוח / 2 לא ידוע, "error": ...}"""
    token = await _get_token()
    params = {
        "clientId":    settings.ttlock_client_id,
        "accessToken": token,
        "lockId":      lock_id,
        "date":        int(_time.time() * 1000),
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/lock/queryOpenState", params=params, timeout=25)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"reachable": False, "state": None, "error": str(e)[:120]}
    if isinstance(data, dict) and data.get("errcode", 0) not in (0, None):
        return {"reachable": False, "state": None,
                "error": f"{data.get('errcode')}: {data.get('errmsg')}"}
    return {"reachable": True, "state": data.get("state"), "error": None}


async def list_lock_records(lock_id: int, start_ms: int, end_ms: int) -> list[dict]:
    """NEW (4.10.26): לוג פתיחות של המנעול (מה שהגייטווי העלה לענן).
    כל רשומה: lockDate (ms), recordType, keyboardPwd (הקוד שהוקש), username, success."""
    token = await _get_token()
    out: list[dict] = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            params = {
                "clientId":    settings.ttlock_client_id,
                "accessToken": token,
                "lockId":      lock_id,
                "startDate":   start_ms,
                "endDate":     end_ms,
                "pageNo":      page,
                "pageSize":    100,
                "date":        int(_time.time() * 1000),
            }
            r = await client.get(f"{BASE_URL}/lockRecord/list", params=params, timeout=20)
            r.raise_for_status()
            data = _check(r.json())
            out.extend(data.get("list", []))
            if page >= int(data.get("pages", 1) or 1) or page >= 10:
                break
            page += 1
    return out


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


def _reserved_codes() -> set[str]:
    """קודים שאסור לתת לאורח: בעלים, מנקה, ו-0000."""
    cleaner = (os.getenv("CLEANER_CODE") or "5555").strip().rstrip("#")
    return {"4708", "0000", cleaner}


def _pick_last4(phone_digits: str, reserved: set[str]) -> str | None:
    """4 הספרות האחרונות של הטלפון; None אם הטלפון קצר מדי או שהקוד שמור."""
    if len(phone_digits) < 7:
        return None
    code = phone_digits[-4:]
    return None if code in reserved else code


def _parse_fixed_codes(raw: str | None, norm, reserved: set[str]) -> dict[str, str]:
    """
    משתנה סביבה FIXED_GUEST_CODES — קוד קבוע לאורח מסוים, לפי טלפון:
        0523274533=2454;0501112222=1357      (מפרידים: ; , רווח או שורה חדשה)
    הטלפון מנורמל (054… / +972… זהים). קוד חייב להיות 4–8 ספרות ולא שמור.
    ערך לא תקין מדולג (עם אזהרה בלוג).
    """
    out: dict[str, str] = {}
    for part in (raw or "").replace("\n", ";").replace(",", ";").replace(" ", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            logger.warning(f"FIXED_GUEST_CODES: skipping '{part}' (missing '=')")
            continue
        ph, code = (x.strip() for x in part.split("=", 1))
        code = code.rstrip("#")
        ph = norm(ph)
        if len(ph) < 7 or not code.isdigit() or not (4 <= len(code) <= 8) or code in reserved:
            logger.warning(f"FIXED_GUEST_CODES: skipping invalid entry for '{ph or part}'")
            continue
        out[ph] = code
    return out


async def _returning_guest_code(booking, db: AsyncSession) -> str | None:
    """
    קוד קבוע-לפי-טלפון לאורח: (א) קוד שהוגדר ידנית ב-FIXED_GUEST_CODES, או
    (ב) לאורח חוזר — 4 הספרות האחרונות של הטלפון. None = קוד אקראי.
    לא זורק חריגות — כל כשל = None (הזמנה לא נתקעת בגלל זה).
    """
    try:
        from sqlalchemy import select
        from app.models import Booking, is_cancelled_status
        from app.services.booking_guard import norm_phone, notify_owners

        phone = norm_phone(getattr(booking, "guest_phone", None))
        if not phone or not booking.check_in or not booking.check_out:
            return None

        rows = (await db.execute(select(Booking).where(Booking.id != booking.id))).scalars().all()
        active = [o for o in rows
                  if not is_cancelled_status(o.status) and o.check_in and o.check_out]

        reserved = _reserved_codes()
        fixed = _parse_fixed_codes(os.getenv("FIXED_GUEST_CODES"), norm_phone, reserved).get(phone)
        if fixed:
            code, why = fixed, "קוד קבוע שהוגדר לאורח"
        else:
            # אורח חוזר = שהייה קודמת של אותו טלפון שהסתיימה לפני ההגעה הזו
            if not any(norm_phone(o.guest_phone) == phone and o.check_out <= booking.check_in
                       for o in active):
                return None
            code, why = _pick_last4(phone, reserved), "4 הספרות האחרונות של הטלפון"
            if not code:
                return None

        my_locks = set(_resolve_lock_ids(booking.room_name))
        if not my_locks:
            return None

        taken = None
        # (1) הזמנה אחרת חופפת, עם אותו קוד, על אותו מנעול
        for o in active:
            if (o.entry_code or "").rstrip("#") == code \
                    and my_locks & set(_resolve_lock_ids(o.room_name)) \
                    and o.check_in < booking.check_out and booking.check_in < o.check_out:
                taken = f"הזמנה {o.id} ({o.guest_name})"
                break
        # (2) קוד זהה שקיים כבר בפועל במנעול (כולל קוד שלא נמחק עדיין)
        if not taken:
            for lock_id in my_locks:
                try:
                    existing = await list_passcodes(lock_id)
                except Exception as e:  # noqa: BLE001 — אי אפשר לאמת; ממשיכים עם בדיקת ה-DB
                    logger.warning(f"returning-code: list_passcodes({lock_id}) failed: {e}")
                    continue
                if any(str(p.get("keyboardPwd") or "").rstrip("#") == code for p in existing):
                    taken = f"קוד קיים במנעול {lock_id}"
                    break

        if taken:
            logger.warning(f"Booking {booking.id}: guest code {code} taken ({taken}) → random")
            await notify_owners(
                "קוד אורח חוזר תפוס",
                f"{booking.guest_name}: {why} תפוס ({taken}). נוצר קוד אקראי — "
                f"אם זה קוד ישן/ידני במנעול, למחוק אותו ב-TTLock ולהקצות מחדש להזמנה.",
            )
            return None

        logger.info(f"Booking {booking.id}: guest code from: {why}")
        return code
    except Exception as e:  # noqa: BLE001
        logger.error(f"returning-guest code failed for booking {getattr(booking, 'id', '?')}: {e}")
        return None


def _israel_ms(d: date, t: time) -> int:
    """תאריך + שעה בשעון ישראל → epoch ms (נכון גם בשעון חורף/קיץ)."""
    return int(datetime.combine(d, t, tzinfo=TZ).timestamp() * 1000)


def _to_ms(d) -> int:
    """date/datetime (שעון ישראל) -> epoch ms."""
    if isinstance(d, datetime):
        dt = d if d.tzinfo else d.replace(tzinfo=TZ)
    else:
        dt = datetime.combine(d, time(0, 0), tzinfo=TZ)
    return int(dt.timestamp() * 1000)


def _hhmm(val, default: time) -> time:
    try:
        h, m = str(val).strip().split(":")[:2]
        return time(int(h), int(m))
    except Exception:
        return default


def _default_checkout(check_out: date) -> time:
    """יציאה: 14:00 בשבת, 12:00 בשאר הימים — כמו ב-scheduler."""
    return time(14, 0) if check_out.isoweekday() == 6 else time(12, 0)


def _booking_window(booking) -> tuple[int, int]:
    """חלון הקוד לפי ההזמנה: checkin_time/checkout_time אם הוגדרו, אחרת ברירת מחדל."""
    ci = _hhmm(getattr(booking, "checkin_time", None), time(14, 0))
    co = _hhmm(getattr(booking, "checkout_time", None), _default_checkout(booking.check_out))
    return _israel_ms(booking.check_in, ci), _israel_ms(booking.check_out, co)


# ---------------------------------------------------------------------------
# High-level operations (called by routes / scheduler)
# ---------------------------------------------------------------------------
async def assign_passcode_to_booking(booking, db: AsyncSession,
                                     passcode: str | None = None) -> str:
    """
    Create a period passcode on the relevant lock(s) for a booking,
    store entry_code + ttlock_pwd_ids on the booking, commit, return the code.
    """
    lock_ids = _resolve_lock_ids(booking.room_name)
    if not lock_ids:
        logger.error(f"Booking {booking.id}: cannot resolve lock for room '{booking.room_name}'")
        return ""

    code = passcode or booking.entry_code or await _returning_guest_code(booking, db) or _gen_code()
    start_ms, end_ms = _booking_window(booking)

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
    logger.info(f"Booking {booking.id}: passcode {code} set on {pwd_ids} "
                f"({datetime.fromtimestamp(start_ms / 1000, TZ):%d/%m %H:%M} → "
                f"{datetime.fromtimestamp(end_ms / 1000, TZ):%d/%m %H:%M} Israel)")
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
    window as creation (_booking_window). No-op (returns False) if the booking
    has no passcode yet.
    """
    if not booking.ttlock_pwd_ids:
        return False

    start_ms, end_ms = _booking_window(booking)

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
                # תיקון (2.10.26): הנתיב הנכון ב-TTLock הוא keyboardPwd/change
                # (changePeriod לא קיים — כל עדכון שעות מהדשבורד נכשל בשקט).
                r = await client.post(f"{BASE_URL}/keyboardPwd/change", data=payload, timeout=15)
                if r.status_code >= 300:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                _check(r.json())
            logger.info(f"Booking {booking.id}: TTLock period updated for {entry}")
        except Exception as e:
            logger.error(f"Booking {booking.id}: TTLock change failed for {entry}: {e}")
            ok = False
    return ok
