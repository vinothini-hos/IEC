import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, SessionLocal, ensure_schema_migrations
from .routers import threads, emails, gmail_webhook, specification
from . import sync_service

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
ensure_schema_migrations()

app = FastAPI(title="IEC Mailbox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router)
app.include_router(emails.router)
app.include_router(gmail_webhook.router)
app.include_router(specification.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


async def _poll_gmail_loop():
    """Background auto-sync so the inbox picks up new mail without a
    manual POST /api/threads/sync — no Pub/Sub push endpoint required.
    Syncs once immediately on startup, then on every interval after."""
    while True:
        db = SessionLocal()
        try:
            await asyncio.to_thread(sync_service.sync_recent_threads, db)
        except Exception:
            logger.exception("Background Gmail sync failed")
        finally:
            db.close()
        await asyncio.sleep(settings.gmail_poll_interval_seconds)


@app.on_event("startup")
async def start_background_sync():
    app.state.poll_task = asyncio.create_task(_poll_gmail_loop())


@app.on_event("shutdown")
async def stop_background_sync():
    app.state.poll_task.cancel()
