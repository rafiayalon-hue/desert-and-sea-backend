from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import bookings, guests, locks, messages, settings
from app.api.routes import guests_merge
from app.api.routes import webhook          # NEW
from app.database import engine, Base
from app.scheduler import scheduler         # NEW


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

    # Start APScheduler
    scheduler.start()

    yield  # ── app is running ──────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Desert and Sea — דשבורד ניהול צימרים",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://desert-and-sea.vercel.app",
        "https://*.vercel.app",
        "https://desert-and-sea-production.up.railway.app",
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
app.include_router(guests_merge.router, prefix="/api/guests", tags=["guests"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Desert and Sea"}
