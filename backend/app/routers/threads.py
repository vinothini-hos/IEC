import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas, sync_service
from ..database import get_db

router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.get("", response_model=list[schemas.ThreadListItemOut])
def list_threads(db: Session = Depends(get_db)):
    """Inbox view: one row per thread, newest first."""
    threads = (
        db.query(models.Thread)
        .options(joinedload(models.Thread.emails))
        .order_by(models.Thread.last_message_at.desc())
        .all()
    )
    out = []
    for t in threads:
        latest = t.latest_email
        out.append(schemas.ThreadListItemOut(
            id=t.id,
            gmail_thread_id=t.gmail_thread_id,
            subject=t.subject,
            participants=t.participants,
            last_message_at=t.last_message_at,
            unread_count=t.unread_count,
            latest_snippet=latest.snippet if latest else "",
            latest_direction=latest.direction.value if latest else None,
            extraction_status=t.extraction_status,
            classification_summary=(t.extraction_result or {}).get("classification_summary"),
        ))
    return out


@router.get("/{thread_id}", response_model=schemas.ThreadDetailOut)
def get_thread(thread_id: uuid.UUID, db: Session = Depends(get_db)):
    """Thread view: every email in the thread, chronological."""
    thread = (
        db.query(models.Thread)
        .options(joinedload(models.Thread.emails).joinedload(models.Email.attachments))
        .filter(models.Thread.id == thread_id)
        .first()
    )
    if not thread:
        raise HTTPException(404, "Thread not found")
    return thread


@router.post("/sync")
def sync_threads(max_threads: int = 25, db: Session = Depends(get_db)):
    """Manual pull from Gmail (also called by the Pub/Sub webhook)."""
    threads = sync_service.sync_recent_threads(db, max_threads)
    return {"synced": len([t for t in threads if t])}
