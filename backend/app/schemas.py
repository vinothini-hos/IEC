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
    extraction_status: Optional[str] = None
    classification_summary: Optional[str] = None
    # whether the later modules have saved results for this thread - lets their
    # pickers list only the RFQs already worked on
    has_similar_projects: bool = False
    has_design_calc: bool = False
    draft_boq_drawings: int = 0

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


class ClarificationIn(BaseModel):
    equipment_index: int = 0


class SimilarProjectsIn(BaseModel):
    equipment_index: int = 0


class DraftBoqCountIn(BaseModel):
    index: int  # position in the drawing's components list
    count: Optional[int] = None  # None reverts to the detected count


class DesignCalcIn(BaseModel):
    equipment_index: int = 0


class DesignCalcCellIn(BaseModel):
    equipment_index: int = 0
    sheet_key: str
    table_id: str
    row_id: str
    key: str  # value1 / value2 / value / an extra column
    value: str | float | None = None  # None or "" reverts to the calc JSON's formula
