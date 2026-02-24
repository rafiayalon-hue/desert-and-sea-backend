from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import bookings, guests, locks, messages

app = FastAPI(title="Desert and Sea", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bookings.router, prefix="/api/bookings", tags=["הזמנות"])
app.include_router(guests.router, prefix="/api/guests", tags=["אורחים"])
app.include_router(locks.router, prefix="/api/locks", tags=["מנעולים"])
app.include_router(messages.router, prefix="/api/messages", tags=["הודעות"])


@app.get("/health")
async def health():
    return {"status": "ok"}
