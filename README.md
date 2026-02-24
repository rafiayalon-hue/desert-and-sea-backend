# Desert and Sea — דשבורד ניהולי לצימרים

מערכת ניהול מלאה לצימרים הכוללת סנכרון הזמנות, ניהול מנעולים חכמים ושליחת הודעות WhatsApp אוטומטיות לאורחים.

## תכונות עיקריות

- **סנכרון הזמנות** מ-MiniHotel עם סטטיסטיקות תפוסה
- **קודי כניסה אוטומטיים** דרך TTLock לפי תאריכי ההזמנה
- **הודעות WhatsApp מתוזמנות** לאורחים: לפני הגעה, קוד כניסה, ויציאה
- **מאגר אורחים חוזרים** עם תמיכה בקמפיינים ממוקדים
- **ממשק בעברית** עם תקשורת רב-לשונית לאורחים (עברית, אנגלית, ערבית, רוסית)

## ארכיטקטורה

```
backend/   Python + FastAPI (API server + scheduler)
frontend/  React + Vite (Hebrew RTL dashboard)
```

**שירותים חיצוניים:**
| שירות | מטרה |
|---|---|
| MiniHotel API | משיכת הזמנות וסטטיסטיקות |
| TTLock API | הנפקת קודי כניסה למנעולים חכמים |
| Twilio WhatsApp | שליחת הודעות לאורחים |
| PostgreSQL | מסד הנתונים הראשי |
| Redis | תור משימות (Celery) |

## התקנה מהירה

### דרישות מוקדמות
- Python 3.12+
- Docker & Docker Compose
- חשבונות API: MiniHotel, TTLock, Twilio

### הרצה עם Docker

```bash
cp .env.example .env
# מלא את ערכי ה-API ב-.env
docker compose up -d
```

### הרצה מקומית (backend)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API זמין בכתובת: http://localhost:8000
תיעוד אוטומטי: http://localhost:8000/docs

## הגדרות נדרשות ב-.env

| משתנה | תיאור |
|---|---|
| `MINIHOTEL_API_KEY` | מפתח API של MiniHotel |
| `MINIHOTEL_PROPERTY_ID` | מזהה הנכס במערכת MiniHotel |
| `TTLOCK_CLIENT_ID` | Client ID מ-TTLock Open Platform |
| `TTLOCK_ACCESS_TOKEN` | Access Token של TTLock |
| `TWILIO_ACCOUNT_SID` | Account SID מ-Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token מ-Twilio |
| `DATABASE_URL` | כתובת PostgreSQL |

## מיפוי חדרים למנעולים

אחרי הגדרת TTLock, עדכן את `ROOM_LOCK_MAP` ב-`backend/app/api/routes/locks.py`:

```python
ROOM_LOCK_MAP = {
    "חדר מדבר": 123456,  # Lock ID מ-TTLock
    "חדר ים":   654321,
}
```
