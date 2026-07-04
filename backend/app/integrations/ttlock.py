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
import time
import httpx

from app.config import settings

# TTLock EU endpoints
AUTH_URL = "https://euapi.ttlock.com/oauth2/token"
BASE_URL = "https://euapi.ttlock.com/v3"

# Passcode type: 1=one-time, 2=permanent, 3=period(timed), 4=erase
PASSCODE_TYPE_PERIOD = 3
# addType: 1=via Bluetooth, 2=via gateway (remote)
ADD_TYPE_GATEWAY = 2


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
