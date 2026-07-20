from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
import os

from app.api.routes import bookings, guests, locks, messages, settings
from app.api.routes import guests_merge
from app.api.routes import webhook          # NEW
from app.api.routes import whatsapp_inbound  # NEW — הודעות WhatsApp נכנסות
from app.api.routes import campaigns         # NEW — רשימת פנייה לאורחי עבר
from app.api.routes import public_checkin   # NEW — עמוד קוד כניסה באתר הציבורי
from app.database import engine, Base
from app.scheduler import scheduler, run_reconciliation_now         # NEW


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # existing columns (idempotent)
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS guest_email VARCHAR(200)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS country VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS adults INTEGER DEFAULT 1"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS children INTEGER DEFAULT 0"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS balance NUMERIC(10,2) DEFAULT 0"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS source VARCHAR(100)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS notes TEXT"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_link VARCHAR(500)"))
        # new column for custom checkout time
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS checkout_time VARCHAR(10)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS checkin_time VARCHAR(10)"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_returning_guest BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS ttlock_pwd_ids TEXT"))
        await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS proposed_entry_code VARCHAR(20)"))

        # message_log table (idempotent)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS message_log (
                id           SERIAL PRIMARY KEY,
                booking_id   INTEGER REFERENCES bookings(id),
                guest_id     INTEGER,
                phone        VARCHAR(30),
                message_type VARCHAR(50),
                body         TEXT,
                status       VARCHAR(20),
                twilio_sid   VARCHAR(100),
                created_at   TIMESTAMP DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_message_log_booking_type "
            "ON message_log (booking_id, message_type) "
            "WHERE booking_id IS NOT NULL"
        ))

        # NEW (17.7.26): שיחות דו-כיווניות — עד עכשיו message_logs (רבים —
        # זה שם הטבלה האמיתי שה-ORM כותב אליו, לא message_log היחיד שנוצר
        # למעלה) היה מיועד רק להודעות יוצאות. direction מבדיל
        # 'inbound'/'outbound' כדי לבנות תצוגת שיחה אמיתית. ברירת מחדל
        # 'outbound' לרשומות קיימות — כולן היו הודעות שהעסק שלח.
        await conn.execute(text(
            "ALTER TABLE message_logs ADD COLUMN IF NOT EXISTS direction VARCHAR(10) DEFAULT 'outbound'"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_message_logs_phone ON message_logs (phone)"
        ))

        # checkin_tokens table (idempotent) — NEW: עמוד קוד כניסה באתר הציבורי
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS checkin_tokens (
                id          SERIAL PRIMARY KEY,
                booking_id  INTEGER REFERENCES bookings(id) NOT NULL,
                token       VARCHAR(64) UNIQUE NOT NULL,
                expires_at  DATE NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_checkin_tokens_booking_id "
            "ON checkin_tokens (booking_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_checkin_tokens_token "
            "ON checkin_tokens (token)"
        ))

        # NEW (16.7.26): פרטי חשבון בנק — כדי שאבישג תוכל לגשת ולשלוח
        # לאורחים שמבקשים לשלם בהעברה בנקאית, בלי לחפש אצל רפי כל פעם.
        await conn.execute(text("ALTER TABLE business_settings ADD COLUMN IF NOT EXISTS bank_name VARCHAR(200)"))
        await conn.execute(text("ALTER TABLE business_settings ADD COLUMN IF NOT EXISTS bank_branch VARCHAR(200)"))
        await conn.execute(text("ALTER TABLE business_settings ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(50)"))
        await conn.execute(text("ALTER TABLE business_settings ADD COLUMN IF NOT EXISTS bank_account_holder VARCHAR(200)"))

    # Start APScheduler
    scheduler.start()

    # רשת ביטחון: משלים מיד כל entry_code/checkout job שאבד בדיפלוי
    # האחרון (ה-scheduler הוא in-memory בלבד — ראו app/scheduler.py),
    # במקום לחכות עד לסבב המחזורי הראשון (עד 30 דקות).
    await run_reconciliation_now()

    yield  # ── app is running ──────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Desert and Sea — דשבורד ניהול צימרים",
    version="1.0.0",
    lifespan=lifespan,
)
static_dir = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://desert-and-sea.vercel.app",
        "https://*.vercel.app",
        "https://desert-and-sea-production.up.railway.app",
        "https://desert-sea.co.il",             # NEW — האתר הציבורי (וורדפרס) קורא ל-/public/entry-code משם
        "https://www.desert-sea.co.il",          # NEW — הדומיין האמיתי (עם מקף)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bookings.router, prefix="/api/bookings",  tags=["bookings"])
app.include_router(guests.router,   prefix="/api/guests",    tags=["guests"])
app.include_router(locks.router,    prefix="/api/locks",     tags=["locks"])
app.include_router(messages.router, prefix="/api/messages",  tags=["messages"])
app.include_router(settings.router, prefix="/api/settings",  tags=["settings"])
app.include_router(webhook.router,  prefix="/api/webhook",   tags=["webhook"])  # NEW
app.include_router(whatsapp_inbound.router, prefix="/api/webhook", tags=["webhook"])  # NEW — /api/webhook/whatsapp-inbound
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])  # NEW
app.include_router(guests_merge.router, prefix="/api/guests", tags=["guests"])
app.include_router(public_checkin.router)   # NEW — /public/entry-code/{token}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Desert and Sea"}
