from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import gmail_service, sync_service
from ..database import get_db

router = APIRouter(prefix="/api/gmail", tags=["gmail"])


@router.post("/webhook")
async def gmail_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives Gmail Pub/Sub push notifications (topic: gmail-notifications,
    subscription: gmail-notifications-sub). Gmail's push payload only
    carries a historyId, not the message itself, so on receipt we just
    pull the latest inbox threads. Good enough for a first pass; swap
    for users.history.list(startHistoryId=...) later to sync precisely.
    """
    envelope = await request.json()
    history_id = gmail_service.decode_pubsub_history_id(envelope)

    sync_service.sync_recent_threads(db, max_threads=10)

    return {"status": "ok", "history_id": history_id}
