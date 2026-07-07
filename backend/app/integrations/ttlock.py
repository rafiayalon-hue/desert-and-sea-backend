"""
TTLock API integration for generating and managing door entry codes.
Docs: https://euopen.ttlock.com/doc/api/v3

Authentication model:
  clientId + clientSecret  → identify the developer app
  username + password(MD5) → identify the lock account
  → together produce an access_token (valid ~90 days, refreshable)

Passcode model (gateway / remote):
  keyboardPwd/add  — add a passcode with DIGITS YOU CHOOSE (keyboardPwd)
  keyboardPwdType=3 (period) with startDate/endDate  — time-limited code
  addType=2  — program remotely via the gateway (no Bluetooth proximity)
"""
import hashlib
import random
import re
import time
from datetime import datetime

import httpx

from app.config import settings

# TTLock EU endpoints
AUTH_URL = "https://euapi.ttlock.com/oauth2/token"
BASE_URL = "https://euapi.ttlock.com/v3"

# Passcode type: 1=one-time, 2=permanent, 3=period(timed), 4=erase
PASSCODE_TYPE_PERIOD = 3
# addType: 1=via Bluetooth, 2=via gateway (remote)
ADD_TYPE_GATEWAY = 2

# מיפוי חדר → lock_id (מאומת מול אפליקציית TTLock)
LOCK_IDS = {
    "desert": 18201474,  # צימר מדבר
    "sea": 18201274,     # צימר ים
}


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


class TTLockError(Exception):
    """Raised when the TTLock API returns an errcode in the body."""
    def __init__(self, errcode, errmsg):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"TTLock error {errcode}: {errmsg}")


class TTLockClient:
    def __init__(self):
        self.client_id     = settings.ttlock_client_id
        self.client_secret = settings.ttlock_client_secret
        self.username      = settings.ttlock_username
        self.password      = settings.ttlock_password
        self._access_token: str | None = None
        self._token_expires_at: int = 0  # epoch ms

    # ── Authentication ──────────────────────────────────────────────────
    async def _fetch_token(self) -> str:
        """Get a fresh access token using username + MD5(password)."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                AUTH_URL,
                data={
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret,
                    "username": self.username,
                    "password": _md5(self.password),
                },
            )
            resp.raise_for_status()
            body = resp.json()
            if "access_token" not in body:
                raise TTLockError(body.get("errcode", -1), body.get("errmsg", "no access_token in response"))
            self._access_token = body["access_token"]
            # expires_in is in seconds; refresh 1 day early for safety
            expires_in = int(body.get("expires_in", 7776000))  # default ~90d
            self._token_expires_at = _now_ms() + (expires_in - 86400) * 1000
            return self._access_token

    async def _get_token(self) -> str:
        if not self._access_token or _now_ms() >= self._token_expires_at:
            return await self._fetch_token()
        return self._access_token

    async def _base_params(self) -> dict:
        return {
            "clientId": self.client_id,
            "accessToken": await self._get_token(),
            "date": _now_ms(),
        }

    def _check(self, body: dict) -> dict:
        """TTLock returns errcode=0 on success (or omits it)."""
        errcode = body.get("errcode", 0)
        if errcode not in (0, None):
            raise TTLockError(errcode, body.get("errmsg", "unknown error"))
        return body

    # ── Passcodes ───────────────────────────────────────────────────────
    async def add_passcode(
        self,
        lock_id: int,
        passcode: str,
        passcode_name: str,
        start_date: int,
        end_date: int,
    ) -> dict:
        """
        Add a time-limited passcode with CHOSEN digits, via gateway.
        passcode: 4-9 digit string you choose (same digits for returning guests).
        start_date / end_date: Unix timestamps in milliseconds.
        Returns dict containing keyboardPwdId.
        """
        params = await self._base_params()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{BASE_URL}/keyboardPwd/add",
                data={
                    **params,
                    "lockId": lock_id,
                    "keyboardPwd": passcode,
                    "keyboardPwdName": passcode_name,
                    "keyboardPwdType": PASSCODE_TYPE_PERIOD,
                    "startDate": start_date,
                    "endDate": end_date,
                    "addType": ADD_TYPE_GATEWAY,
                },
            )
            resp.raise_for_status()
            return self._check(resp.json())

    async def change_passcode(
        self,
        lock_id: int,
        keyboard_pwd_id: int,
        start_date: int,
        end_date: int,
        new_passcode: str | None = None,
    ) -> dict:
        """
        Change validity period (and optionally digits) of an EXISTING passcode,
        via gateway. Used to re-activate a returning guest's code with a new window.
        """
        params = await self._base_params()
        data = {
            **params,
            "lockId": lock_id,
            "keyboardPwdId": keyboard_pwd_id,
            "startDate": start_date,
            "endDate": end_date,
            "changeType": ADD_TYPE_GATEWAY,  # 2 = via gateway
        }
        if new_passcode:
            data["newKeyboardPwd"] = new_passcode
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{BASE_URL}/keyboardPwd/change", data=data)
            resp.raise_for_status()
            return self._check(resp.json())

    async def delete_passcode(self, lock_id: int, keyboard_pwd_id: int) -> dict:
        """Delete a passcode via gateway."""
        params = await self._base_params()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{BASE_URL}/keyboardPwd/delete",
                data={
                    **params,
                    "lockId": lock_id,
                    "keyboardPwdId": keyboard_pwd_id,
                    "deleteType": ADD_TYPE_GATEWAY,  # 2 = via gateway
                },
            )
            resp.raise_for_status()
            return self._check(resp.json())

    async def list_locks(self) -> list[dict]:
        params = await self._base_params()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{BASE_URL}/lock/list",
                params={**params, "pageNo": 1, "pageSize": 50},
            )
            resp.raise_for_status()
            body = resp.json()
            self._check(body)
            return body.get("list", [])

    async def list_passcodes(self, lock_id: int) -> list[dict]:
        """List all passcodes on a lock (to find a returning guest's existing code)."""
        params = await self._base_params()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{BASE_URL}/lock/listKeyboardPwd",
                params={**params, "lockId": lock_id, "pageNo": 1, "pageSize": 100},
            )
            resp.raise_for_status()
            body = resp.json()
            self._check(body)
            return body.get("list", [])


ttlock_client = TTLockClient()


# ── Module-level helpers expected by app.api.routes.locks ───────────────

def _resolve_lock_id(room_name: str) -> int:
    """
    ממפה את שם החדר (כפי שמגיע מ-MiniHotel, למשל 'צימר מדבר' / 'צימר ים')
    ל-lock_id הנכון. בודק לפי הימצאות המילה 'מדבר' או 'ים' בתוך השם,
    כדי לא להיות תלוי בניסוח מדויק (רישיות/רווחים/עברית-אנגלית).

    כולל גם תמיכה ב-'sesert' — שגיאת כתיב היסטורית (צריך 'desert') שקיימת
    בחלק מהנתונים הישנים (יבוא Excel / webhook גרסה קודמת). ה-frontend
    (useBookings.js) כבר מזהה את הכינוי הזה — כאן מיושר לאותה התנהגות.
    """
    name = room_name or ""
    lowered = name.lower()
    if "מדבר" in name or "desert" in lowered or "sesert" in lowered:
        return LOCK_IDS["desert"]
    if "ים" in name or "sea" in lowered:
        return LOCK_IDS["sea"]
    raise ValueError(f"לא ניתן לזהות חדר (desert/sea) מתוך room_name: {room_name!r}")


def _parse_hhmm(value: str | None, default_hour: int, default_minute: int = 0) -> tuple[int, int]:
    """ממיר מחרוזת 'HH:MM' לזוג (שעה, דקה). נופל לברירת מחדל אם ריק/לא תקין."""
    try:
        hour_str, minute_str = (value or "").split(":")
        return int(hour_str), int(minute_str)
    except (ValueError, AttributeError):
        return default_hour, default_minute


async def get_lock_status(lock_id: int) -> dict:
    """
    סטטוס מנעול בודד — סוללה, חיבור וכו'.
    ה-API של TTLock לא חושף endpoint לפרטי מנעול בודד, אז אנחנו
    מסננים מתוך lock/list (שמחזיר את כל המנעולים בחשבון).
    """
    locks = await ttlock_client.list_locks()
    for lock in locks:
        if lock.get("lockId") == lock_id:
            return lock
    raise TTLockError(-1, f"lockId {lock_id} לא נמצא ב-list_locks()")


async def list_passcodes(lock_id: int) -> list[dict]:
    """עטיפה ברמת מודול (locks.py מייבא פונקציה, לא מתודת מחלקה)."""
    return await ttlock_client.list_passcodes(lock_id)


async def assign_passcode_to_booking(booking, db, passcode: str | None = None) -> str:
    """
    יוצר קוד כניסה להזמנה במנעול הנכון (לפי booking.room_name),
    שומר אותו ב-booking.entry_code, ומחזיר את הקוד.

    אם passcode לא סופק:
      - ברירת המחדל היא 4 הספרות האחרונות של מספר הטלפון של האורח
        (עקבי עם המוסכמה הקיימת בעסק — כל הקודים ההיסטוריים הם 4 ספרות,
        ומזכה גם לאורח לזכור קל יותר).
      - אם אין מספר טלפון עם לפחות 4 ספרות — נוצר קוד רנדומלי בן 4 ספרות.

    חלון התוקף: לפי booking.checkin_time / booking.checkout_time בפועל
    (כולל דקות — חשוב לשבתות עם שעת יציאה חריגה כמו 16:30), עם ברירת
    מחדל של 14:00/12:00 אם לא נקבעה שעה ידנית להזמנה הזו.
    שם הקוד במנעול נשמר כ-'BK{booking.id}' כדי שנוכל לאתר ולמחוק אותו
    בבירור (booking.entry_code בלבד לא מספיק כי אין עמודת keyboard_pwd_id).
    """
    lock_id = _resolve_lock_id(booking.room_name)

    if not passcode:
        digits = re.sub(r"\D", "", booking.guest_phone or "")
        if len(digits) >= 4:
            passcode = digits[-4:]
        else:
            passcode = str(random.randint(1000, 9999))

    checkin_hour, checkin_minute = _parse_hhmm(getattr(booking, "checkin_time", None), 14, 0)
    checkout_hour, checkout_minute = _parse_hhmm(getattr(booking, "checkout_time", None), 12, 0)

    start_dt = datetime.combine(booking.check_in, datetime.min.time()).replace(hour=checkin_hour, minute=checkin_minute)
    end_dt = datetime.combine(booking.check_out, datetime.min.time()).replace(hour=checkout_hour, minute=checkout_minute)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    passcode_name = f"BK{booking.id}"

    await ttlock_client.add_passcode(
        lock_id=lock_id,
        passcode=passcode,
        passcode_name=passcode_name,
        start_date=start_ms,
        end_date=end_ms,
    )

    booking.entry_code = passcode
    db.add(booking)
    await db.commit()

    return passcode


async def remove_passcode_after_checkout(booking, db) -> bool:
    """
    מוחק את קוד הכניסה של ההזמנה מהמנעול (מאותר לפי השם 'BK{booking.id}'
    שנשמר בזמן היצירה), ומנקה את booking.entry_code.
    מחזיר True אם נמצא ונמחק קוד בפועל, False אם לא היה קוד להזמנה הזו.
    """
    lock_id = _resolve_lock_id(booking.room_name)
    passcode_name = f"BK{booking.id}"

    passcodes = await ttlock_client.list_passcodes(lock_id)
    target = next((p for p in passcodes if p.get("keyboardPwdName") == passcode_name), None)

    booking.entry_code = None
    db.add(booking)
    await db.commit()

    if not target:
        return False

    await ttlock_client.delete_passcode(lock_id, target["keyboardPwdId"])
    return True
