import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import gmail_service, models, schemas, sync_service
from ..database import get_db

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.post("/send", response_model=schemas.ThreadDetailOut)
def send_email(
    to: str = Form(...),
    cc: Optional[str] = Form(""),
    subject: str = Form(...),
    body_text: str = Form(...),
    thread_id: Optional[uuid.UUID] = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """
    Sends a new email, or a reply when thread_id is provided. Sends through
    the real Gmail API, then re-syncs that thread so the returned view
    reflects exactly what Gmail has (correct message id, timestamp, etc).
    Uploaded files are attached to the outgoing message but not persisted
    to disk — only attachments we *receive* are saved locally (see
    sync_service.upsert_thread_from_gmail).
    """
    gmail_thread_id = None
    in_reply_to = None

    if thread_id:
        thread = db.query(models.Thread).filter_by(id=thread_id).first()
        if not thread:
            raise HTTPException(404, "Thread not found")
        gmail_thread_id = thread.gmail_thread_id
        last_email = thread.latest_email
        if last_email:
            in_reply_to = last_email.gmail_message_id

    attachments = [
        {
            "filename": f.filename,
            "mime_type": f.content_type or "application/octet-stream",
            "content": f.file.read(),
        }
        for f in files
    ]

    sent = gmail_service.send_email(
        to=to,
        subject=subject,
        body_text=body_text,
        cc=cc,
        gmail_thread_id=gmail_thread_id,
        in_reply_to_message_id=in_reply_to,
        attachments=attachments or None,
    )

    resulting_thread_id = sent["threadId"]
    thread = sync_service.upsert_thread_from_gmail(db, resulting_thread_id)
    return thread


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: uuid.UUID, db: Session = Depends(get_db)):
    attachment = db.query(models.Attachment).filter_by(id=attachment_id).first()
    if not attachment or not attachment.local_path or not os.path.exists(attachment.local_path):
        raise HTTPException(404, "Attachment not available for download")
    return FileResponse(
        attachment.local_path, filename=attachment.filename, media_type=attachment.mime_type
    )


@router.patch("/{email_id}/read", response_model=schemas.EmailOut)
def mark_read(email_id: uuid.UUID, payload: schemas.MarkReadIn, db: Session = Depends(get_db)):
    email = db.query(models.Email).filter_by(id=email_id).first()
    if not email:
        raise HTTPException(404, "Email not found")
    email.is_read = payload.is_read
    db.commit()
    db.refresh(email)
    return email
