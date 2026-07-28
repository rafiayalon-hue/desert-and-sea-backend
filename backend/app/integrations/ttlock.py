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
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

# TTLock EU endpoints
AUTH_URL = "https://euapi.ttlock.com/oauth2/token"
BASE_URL = "https://euapi.ttlock.com/v3"

# NEW (15.7.26): כל שעות הכניסה/יציאה הן זמן ישראל — לא זמן השרת (Railway
# רץ ב-UTC). בלי לקבוע tzinfo במפורש, datetime.timestamp() על אובייקט
# "תמים" (naive) מניח בטעות שהשעה היא לפי אזור הזמן של השרת, מה שיצר
# הפרש קבוע של 3 שעות בין מה שהוזן בדשבורד למה שבאמת נכתב במנעול
# (התגלה בבדיקת הזמנה BK446: 12:30/16:00 בדשבורד → 15:30/19:00 בפועל
# במנעול — הפרש קבוע ועקבי בשני הכיוונים, בדיוק UTC מול Asia/Jerusalem).
IL_TZ = ZoneInfo("Asia/Jerusalem")

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

def _resolve_lock_ids(room_name: str) -> list[int]:
    """
    ממפה את שם החדר (כפי שמגיע מ-MiniHotel, למשל 'צימר מדבר' / 'צימר ים')
    ל-lock_id(ים) הנכון(ים). בודק לפי הימצאות המילה 'מדבר' או 'ים' בתוך השם,
    כדי לא להיות תלוי בניסוח מדויק (רישיות/רווחים/עברית-אנגלית).

    כולל גם תמיכה ב-'sesert' — שגיאת כתיב היסטורית (צריך 'desert') שקיימת
    בחלק מהנתונים הישנים (יבוא Excel / webhook גרסה קודמת). ה-frontend
    (useBookings.js) כבר מזהה את הכינוי הזה — כאן מיושר לאותה התנהגות.

    IMPORTANT — 'des_sea' (הנכס השלישי במיניהוטל, ששני הצימרים ביחד,
    בעיקר להזמנות Airbnb): נבדק ראשון, ובנפרד מ-'desert'/'sea' הבודדים,
    כי 'sea' הוא תת-מחרוזת של 'des_sea' — בדיקת 'sea in room' לפני הבדיקה
    הזו הייתה מחזירה בטעות רק את מנעול הים ומשאירה את הצימר מדבר בלי קוד.
    הנורמליזציה (lower + strip + הסרת רווחים) עקבית עם bookings.py
    (occupancy_stats), כדי ששני המקומות יזהו 'des_sea' באותו אופן בדיוק.
    """
    normalised = (room_name or "").strip().lower().replace(" ", "")

    if "des_sea" in normalised:
        return [LOCK_IDS["desert"], LOCK_IDS["sea"]]
    if "מדבר" in (room_name or "") or "desert" in normalised or "sesert" in normalised:
        return [LOCK_IDS["desert"]]
    if "ים" in (room_name or "") or "sea" in normalised:
        return [LOCK_IDS["sea"]]
    raise ValueError(f"לא ניתן לזהות חדר (desert/sea/des_sea) מתוך room_name: {room_name!r}")


def _parse_hhmm(value: str | None, default_hour: int, default_minute: int = 0) -> tuple[int, int]:
    """ממיר מחרוזת 'HH:MM' לזוג (שעה, דקה). נופל לברירת מחדל אם ריק/לא תקין."""
    try:
        hour_str, minute_str = (value or "").split(":")
        return int(hour_str), int(minute_str)
    except (ValueError, AttributeError):
        return default_hour, default_minute


def _to_il_ms(check_date, hour: int, minute: int) -> int:
    """
    ממיר תאריך + שעה (שהיא תמיד זמן ישראל, לפי איך שהמשתמשים מזינים אותה
    בדשבורד) ל-Unix timestamp במילישניות, עם אזור הזמן הנכון קבוע במפורש.
    זה המקום היחיד שממיר תאריך/שעה ל-ms בקובץ הזה — כל קריאה אחרת עוברת
    כאן, כדי שלא יהיה עוד מקום ששוכח לקבוע tzinfo.
    """
    dt = datetime.combine(check_date, datetime.min.time()).replace(
        hour=hour, minute=minute, tzinfo=IL_TZ
    )
    return int(dt.timestamp() * 1000)


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
    יוצר קוד כניסה להזמנה במנעול(ים) הנכון(ים) (לפי booking.room_name),
    שומר אותו ב-booking.entry_code, ומחזיר את הקוד.

    אם ה-room_name הוא הזמנה משולבת (des_sea — שני הצימרים ביחד),
    אותו קוד נוצר על שני המנעולים בבת אחת, כדי שלאורח יהיה קוד אחד
    שפותח את שתי הדלתות. ה-keyboardPwdId של כל מנעול נשמר ב-
    booking.ttlock_pwd_ids (מופרד בפסיקים), כדי שמחיקה בהמשך תהיה
    מדויקת (במקום להסתמך רק על חיפוש לפי שם).

    אם יצירת הקוד על מנעול שני נכשלת אחרי שהראשון כבר נוצר — מוחקים
    את מה שכבר נוצר ומעלים את השגיאה הלאה, כדי לא להשאיר מצב חצי-מוצלח
    (קוד שעובד רק על דלת אחת מתוך שתיים, בלי שאף אחד ידע).

    הזמנה שבוטלה (status == 'cancelled') לא מקבלת קוד בכלל — זה מגן
    גם מפני ה-job המתוזמן וגם מפני ריצת ה-reconciliation, בלי תלות
    בכך שמישהו זכר לבטל את ה-job הספציפי.
    """
    if (booking.status or "").strip().lower() == "cancelled":
        raise ValueError(f"הזמנה {booking.id} בוטלה — לא יוצרים קוד כניסה")

    lock_ids = _resolve_lock_ids(booking.room_name)

    if not passcode:
        digits = re.sub(r"\D", "", booking.guest_phone or "")
        if len(digits) >= 4:
            passcode = digits[-4:]
        else:
            passcode = str(random.randint(1000, 9999))

    checkin_hour, checkin_minute = _parse_hhmm(getattr(booking, "checkin_time", None), 14, 0)
    checkout_hour, checkout_minute = _parse_hhmm(getattr(booking, "checkout_time", None), 12, 0)

    # NEW (15.7.26): קבוע Asia/Jerusalem במפורש — ראו IL_TZ / _to_il_ms
    # למעלה. זה מה שהיה חסר וגרם להפרש של 3 שעות בין מה שהוזן בדשבורד
    # למה שבאמת נכתב במנעול.
    start_ms = _to_il_ms(booking.check_in, checkin_hour, checkin_minute)
    end_ms = _to_il_ms(booking.check_out, checkout_hour, checkout_minute)

    # NEW (15.7.26): שם האורח מוצג באפליקציית TTLock ("שם" ליד הקוד)
    # במקום המזהה הפנימי BK{id} — קריא בשטח למי שמסתכל באפליקציה.
    passcode_name = (booking.guest_name or f"BK{booking.id}").strip()

    # NEW (28.7.26): אם הקוד (בד"כ 4 ספרות אחרונות של הטלפון) כבר קיים
    # כפעיל על אותו מנעול — למשל מהזמנה קודמת/חופפת של אותו אורח שעדיין
    # לא נמחקה — TTLock דוחה עם errcode -3007 ("same passcode already
    # exists"). זה לא היה מטופל בכלל, וגרם לכישלון שקט של יצירת הקוד
    # (התגלה בהזמנה 472, אולגה דרור). התיקון: בהתנגשות כזו, מגרילים קוד
    # אקראי חדש ומנסים שוב, עד כמה פעמים.
    MAX_PASSCODE_ATTEMPTS = 5
    created_pwd_ids: list[str] = []

    for attempt in range(1, MAX_PASSCODE_ATTEMPTS + 1):
        created_pwd_ids = []
        try:
            for lock_id in lock_ids:
                result = await ttlock_client.add_passcode(
                    lock_id=lock_id,
                    passcode=passcode,
                    passcode_name=passcode_name,
                    start_date=start_ms,
                    end_date=end_ms,
                )
                pwd_id = result.get("keyboardPwdId")
                if pwd_id is not None:
                    created_pwd_ids.append(f"{lock_id}:{pwd_id}")
            break  # הצליח על כל המנעולים — יוצאים מלולאת הניסיונות
        except Exception as e:
            # נכשל באמצע (למשל על המנעול השני) — מנקים את מה שכבר נוצר
            # כדי לא להשאיר קוד יתום שפותח רק דלת אחת מתוך שתיים.
            for entry in created_pwd_ids:
                lid_str, pwd_id_str = entry.split(":")
                try:
                    await ttlock_client.delete_passcode(int(lid_str), int(pwd_id_str))
                except Exception:
                    pass  # best-effort cleanup; השגיאה המקורית חשובה יותר

            is_collision = isinstance(e, TTLockError) and e.errcode == -3007
            if is_collision and attempt < MAX_PASSCODE_ATTEMPTS:
                passcode = str(random.randint(1000, 9999))
                continue
            raise

    booking.entry_code = passcode
    booking.ttlock_pwd_ids = ",".join(created_pwd_ids)
    db.add(booking)
    await db.commit()

    return passcode


async def update_passcode_window(booking, db) -> bool:
    """
    מעדכן את חלון התוקף **בפועל במנעול** לפי checkin_time/checkout_time
    העדכניים של ההזמנה — נקרא מ-bookings.py כשמתקנים שעות ידנית אחרי
    שקוד כבר נוצר (למשל יציאה מאוחרת בסופ"ש). בלי זה, תיקון ידני
    בדשבורד היה משנה רק את מה שמוצג במסך, לא את מה שה-TTLock אוכף בפועל
    בשטח — האורח היה ננעל בחוץ/פנימה לפי החלון הישן.

    משתמש ב-change_passcode (היה קיים ב-client אבל אף אחד לא קרא לו).
    פועל על כל המנעולים ב-ttlock_pwd_ids (גם עבור des_sea — שני המנעולים).
    מחזיר True אם עודכן בפועל, False אם אין קוד קיים לעדכן (אין מה לעשות).
    """
    if not booking.entry_code or not booking.ttlock_pwd_ids:
        return False

    checkin_hour, checkin_minute = _parse_hhmm(getattr(booking, "checkin_time", None), 14, 0)
    checkout_hour, checkout_minute = _parse_hhmm(getattr(booking, "checkout_time", None), 12, 0)

    # NEW (15.7.26): אותו תיקון אזור זמן כמו ב-assign_passcode_to_booking —
    # ראו IL_TZ / _to_il_ms למעלה.
    start_ms = _to_il_ms(booking.check_in, checkin_hour, checkin_minute)
    end_ms = _to_il_ms(booking.check_out, checkout_hour, checkout_minute)

    updated_any = False
    for entry in booking.ttlock_pwd_ids.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        lid_str, pwd_id_str = entry.split(":", 1)
        try:
            await ttlock_client.change_passcode(int(lid_str), int(pwd_id_str), start_ms, end_ms)
            updated_any = True
        except Exception:
            pass  # best-effort — לא עוצרים את שמירת הבקינג בגלל זה

    return updated_any


async def remove_passcode_after_checkout(booking, db) -> bool:
    """
    מוחק את קוד הכניסה של ההזמנה מהמנעול(ים) הרלוונטי(ים).

    אם booking.ttlock_pwd_ids קיים (נשמר בזמן היצירה) — משתמשים בו
    למחיקה מדויקת של כל lock_id:keyboardPwdId בלי צורך בחיפוש.
    אחרת (הזמנות ישנות שנוצרו לפני התוספת הזו) — נופלים חזרה לחיפוש
    לפי השם 'BK{booking.id}' בכל המנעולים הרלוונטיים ל-room_name.

    מנקה תמיד את booking.entry_code / ttlock_pwd_ids בסוף, גם אם לא
    נמצא קוד בפועל (למקרה שכבר נמחק, או שמעולם לא נוצר).
    מחזיר True אם נמצא ונמחק קוד בפועל, False אם לא היה קוד להזמנה הזו.
    """
    # NEW (15.7.26): שם האורח הוא הזיהוי העיקרי כעת — 'BK{id}' עדיין
    # נבדק כ-fallback לקודים ישנים שנוצרו לפני שינוי הכינוי.
    passcode_name = (booking.guest_name or "").strip()
    legacy_name = f"BK{booking.id}"
    deleted_any = False

    if booking.ttlock_pwd_ids:
        for entry in booking.ttlock_pwd_ids.split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            lid_str, pwd_id_str = entry.split(":", 1)
            try:
                await ttlock_client.delete_passcode(int(lid_str), int(pwd_id_str))
                deleted_any = True
            except Exception:
                pass  # ייתכן שכבר נמחק ידנית — לא עוצרים בגללו
    else:
        try:
            lock_ids = _resolve_lock_ids(booking.room_name)
        except ValueError:
            lock_ids = []
        for lock_id in lock_ids:
            passcodes = await ttlock_client.list_passcodes(lock_id)
            target = next(
                (p for p in passcodes if p.get("keyboardPwdName") in (passcode_name, legacy_name)),
                None,
            )
            if target:
                await ttlock_client.delete_passcode(lock_id, target["keyboardPwdId"])
                deleted_any = True

    booking.entry_code = None
    booking.ttlock_pwd_ids = None
    db.add(booking)
    await db.commit()

    return deleted_any
