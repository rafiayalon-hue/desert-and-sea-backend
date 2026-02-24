"""
TTLock API integration for generating and managing door entry codes.
Docs: https://open.ttlock.com/doc
"""
import time

import httpx

from app.config import settings

BASE_URL = "https://euapi.ttlock.com/v3"


class TTLockClient:
    def __init__(self):
        self.client_id = settings.ttlock_client_id
        self.access_token = settings.ttlock_access_token

    def _base_params(self) -> dict:
        return {
            "clientId": self.client_id,
            "accessToken": self.access_token,
            "date": int(time.time() * 1000),
        }

    async def generate_passcode(
        self,
        lock_id: int,
        passcode_name: str,
        start_date: int,
        end_date: int,
    ) -> dict:
        """
        Generate a time-limited passcode for a lock.
        start_date / end_date: Unix timestamps in milliseconds.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/lock/generatePasscode",
                data={
                    **self._base_params(),
                    "lockId": lock_id,
                    "passcodeName": passcode_name,
                    "startDate": start_date,
                    "endDate": end_date,
                    "passcodeType": 3,  # 3 = timed passcode
                },
            )
            response.raise_for_status()
            return response.json()

    async def delete_passcode(self, lock_id: int, keyboard_pwd_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/lock/deletePasscode",
                data={
                    **self._base_params(),
                    "lockId": lock_id,
                    "keyboardPwdId": keyboard_pwd_id,
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_locks(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/lock/list",
                params={**self._base_params(), "pageNo": 1, "pageSize": 50},
            )
            response.raise_for_status()
            return response.json().get("list", [])


ttlock_client = TTLockClient()
