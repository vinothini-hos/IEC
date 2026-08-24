import enum
import uuid

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ForeignKey, Integer, Enum, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base


class Direction(str, enum.Enum):
    incoming = "incoming"
    outgoing = "outgoing"


class Thread(Base):
    __tablename__ = "threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gmail_thread_id = Column(String, unique=True, nullable=False, index=True)
    subject = Column(String, nullable=False, default="")
    # comma-free list is simplest for a first pass; store as text
    participants = Column(Text, default="")
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    emails = relationship(
        "Email", back_populates="thread",
        cascade="all, delete-orphan", order_by="Email.sent_at",
    )

    @property
    def unread_count(self) -> int:
        return sum(1 for e in self.emails if not e.is_read and e.direction == Direction.incoming)

    @property
    def latest_email(self):
        return self.emails[-1] if self.emails else None


class Email(Base):
    __tablename__ = "emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False, index=True)
    gmail_message_id = Column(String, unique=True, nullable=True, index=True)

    direction = Column(Enum(Direction), nullable=False)
    sender = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    cc = Column(String, default="")
    subject = Column(String, default="")
    snippet = Column(String, default="")
    body_text = Column(Text, default="")
    body_html = Column(Text, nullable=True)

    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, default=False)

    thread = relationship("Thread", back_populates="emails")
    attachments = relationship(
        "Attachment", back_populates="email", cascade="all, delete-orphan"
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    mime_type = Column(String, default="application/octet-stream")
    size_bytes = Column(Integer, default=0)
    gmail_attachment_id = Column(String, nullable=True)
    # Set only for attachments we sent ourselves (saved to disk at send
    # time) — attachments on received mail aren't downloadable yet.
    local_path = Column(String, nullable=True)

    email = relationship("Email", back_populates="attachments")

    @property
    def has_download(self) -> bool:
        return bool(self.local_path)
