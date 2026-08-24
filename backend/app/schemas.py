import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    has_download: bool = False

    model_config = ConfigDict(from_attributes=True)


class EmailOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    direction: str
    sender: str
    recipient: str
    cc: str = ""
    subject: str = ""
    snippet: str = ""
    body_text: str = ""
    body_html: Optional[str] = None
    sent_at: datetime
    is_read: bool
    attachments: list[AttachmentOut] = []

    model_config = ConfigDict(from_attributes=True)


class ThreadListItemOut(BaseModel):
    id: uuid.UUID
    gmail_thread_id: str
    subject: str
    participants: str
    last_message_at: datetime
    unread_count: int
    latest_snippet: str = ""
    latest_direction: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ThreadDetailOut(BaseModel):
    id: uuid.UUID
    gmail_thread_id: str
    subject: str
    participants: str
    emails: list[EmailOut]

    model_config = ConfigDict(from_attributes=True)


class MarkReadIn(BaseModel):
    is_read: bool = True
