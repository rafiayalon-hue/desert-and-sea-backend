from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import bookings, guests, locks, messages, settings
from app.database import engine, Base
app = FastAPI(
    title="Desert and Sea — דשבורד ניהול צימרים",
    version="1.0.0"
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
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
app.include_router(bookings.router, prefix="/api/bookings", tags=["bookings"])
app.include_router(guests.router,   prefix="/api/guests",   tags=["guests"])
app.include_router(locks.router,    prefix="/api/locks",    tags=["locks"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Desert and Sea"}
