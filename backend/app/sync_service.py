from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import gmail_service, models
from .config import settings


def upsert_thread_from_gmail(db: Session, gmail_thread_id: str) -> models.Thread:
    messages = gmail_service.fetch_thread(gmail_thread_id, settings.gmail_user_email)
    if not messages:
        return None

    thread = db.query(models.Thread).filter_by(gmail_thread_id=gmail_thread_id).first()
    if not thread:
        thread = models.Thread(gmail_thread_id=gmail_thread_id)
        db.add(thread)
        db.flush()

    thread.subject = messages[0]["subject"] or thread.subject
    participants = {m["sender"] for m in messages} | {m["recipient"] for m in messages}
    thread.participants = ", ".join(sorted(p for p in participants if p))

    for m in messages:
        existing = db.query(models.Email).filter_by(
            gmail_message_id=m["gmail_message_id"]
        ).first()
        if existing:
            continue  # already synced, immutable once received

        email_row = models.Email(
            thread_id=thread.id,
            gmail_message_id=m["gmail_message_id"],
            direction=m["direction"],
            sender=m["sender"],
            recipient=m["recipient"],
            cc=m["cc"],
            subject=m["subject"],
            snippet=m["snippet"],
            body_text=m["body_text"],
            body_html=m["body_html"],
            sent_at=datetime.fromtimestamp(m["internal_date_ms"] / 1000, tz=timezone.utc),
            is_read=(m["direction"] == "outgoing"),  # sent mail counts as read
        )
        db.add(email_row)
        db.flush()

        for a in m["attachments"]:
            db.add(models.Attachment(
                email_id=email_row.id,
                filename=a["filename"],
                mime_type=a["mime_type"],
                size_bytes=a["size_bytes"] or 0,
                gmail_attachment_id=a["gmail_attachment_id"],
            ))

        thread.last_message_at = email_row.sent_at

    db.commit()
    db.refresh(thread)
    return thread


def sync_recent_threads(db: Session, max_threads: int = 25) -> list[models.Thread]:
    thread_ids = gmail_service.fetch_recent_thread_ids(max_threads)
    return [upsert_thread_from_gmail(db, tid) for tid in thread_ids]
