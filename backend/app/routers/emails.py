import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import gmail_service, models, schemas, sync_service
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.post("/send", response_model=schemas.ThreadDetailOut)
def send_email(payload: schemas.SendEmailIn, db: Session = Depends(get_db)):
    """
    Sends a new email, or a reply when thread_id is provided. Sends through
    the real Gmail API, then re-syncs that thread so the returned view
    reflects exactly what Gmail has (correct message id, timestamp, etc).
    """
    gmail_thread_id = None
    in_reply_to = None

    if payload.thread_id:
        thread = db.query(models.Thread).filter_by(id=payload.thread_id).first()
        if not thread:
            raise HTTPException(404, "Thread not found")
        gmail_thread_id = thread.gmail_thread_id
        last_email = thread.latest_email
        if last_email:
            in_reply_to = last_email.gmail_message_id

    sent = gmail_service.send_email(
        to=payload.to,
        subject=payload.subject,
        body_text=payload.body_text,
        cc=payload.cc,
        gmail_thread_id=gmail_thread_id,
        in_reply_to_message_id=in_reply_to,
    )

    resulting_thread_id = sent["threadId"]
    thread = sync_service.upsert_thread_from_gmail(db, resulting_thread_id)
    return thread


@router.patch("/{email_id}/read", response_model=schemas.EmailOut)
def mark_read(email_id: uuid.UUID, payload: schemas.MarkReadIn, db: Session = Depends(get_db)):
    email = db.query(models.Email).filter_by(id=email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    email.is_read = payload.is_read
    db.commit()
    db.refresh(email)
    return email
