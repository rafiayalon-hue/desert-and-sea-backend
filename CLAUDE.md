# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Desert and Sea" is a Hebrew-language vacation rental (צימרים) management dashboard. It integrates with MiniHotel (bookings), TTLock (smart locks), and Twilio WhatsApp (guest messaging).

## Stack

- **Backend**: Python 3.12 + FastAPI, SQLAlchemy (async), APScheduler, PostgreSQL, Redis
- **Frontend**: React + Vite (Hebrew RTL)
- **Task queue**: Celery + Redis (for future heavy async work; APScheduler handles current scheduling)

## Commands

### Backend
```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload          # dev server on :8000
```

### Docker (full stack)
```bash
docker compose up -d        # start all services
docker compose logs -f      # follow logs
docker compose down         # stop
```

### Database migrations (Alembic)
```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Architecture

```
backend/app/
├── main.py              # FastAPI app, CORS, router registration
├── config.py            # Pydantic Settings — all config from .env
├── database.py          # Async SQLAlchemy engine + Base + get_db()
├── models/              # SQLAlchemy ORM models (Booking, Guest, MessageLog)
├── integrations/
│   ├── minihotel.py     # MiniHotelClient — fetch bookings & occupancy stats
│   ├── ttlock.py        # TTLockClient — generate/delete timed passcodes
│   └── whatsapp.py      # Twilio sender + MESSAGE_TEMPLATES (he/en/ar/ru)
├── api/routes/
│   ├── bookings.py      # /api/bookings — list, sync, occupancy stats
│   ├── guests.py        # /api/guests — list, notes, returning guests
│   ├── locks.py         # /api/locks — list locks, generate entry code per booking
│   └── messages.py      # /api/messages — send, log, campaigns
└── tasks/
    └── scheduler.py     # APScheduler jobs: hourly booking sync, 09:00 daily message dispatch
```

## Key Conventions

- **Language**: Backend code in English; API responses and error messages in Hebrew (e.g., `"אורח לא נמצא"`).
- **Message templates**: All WhatsApp templates live in `integrations/whatsapp.py → MESSAGE_TEMPLATES`. Add new languages there.
- **Room → Lock mapping**: `ROOM_LOCK_MAP` in `api/routes/locks.py` maps Hebrew room names to TTLock lock IDs. Must be populated manually after TTLock setup.
- **Scheduler timezone**: `Asia/Jerusalem` (set in `tasks/scheduler.py`).
- **Message types**: `pre_arrival`, `entry_code`, `checkout`, `campaign`, `manual` — stored in `MessageLog.message_type`.

## External API Notes

- **MiniHotel**: REST API, Bearer token auth. Base URL and exact field names must be verified against MiniHotel's live docs — the integration is a skeleton.
- **TTLock**: Uses `euapi.ttlock.com` (EU server). `passcodeType=3` = timed passcode. Timestamps are milliseconds.
- **Twilio WhatsApp**: Phone numbers must be prefixed with `whatsapp:`. The Twilio sandbox number is used until the account is approved for production.

## Environment

Copy `.env.example` to `.env` and fill all values before running. Never commit `.env`.
