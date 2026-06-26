from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class EmailMode(str, Enum):
    DRAFT_ONLY = "draft"
    DRAFT_AND_APPROVAL = "approval"
    AUTO_SEND = "auto_send"


class EmailType(str, Enum):
    INITIAL = "initial"
    REMINDER = "reminder"
    ESCALATION = "escalation"


class DraftEmailPackage(BaseModel):
    """A complete, ready-to-send email draft linked to the originating action."""

    email_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str
    meeting_id: str

    email_type: EmailType = EmailType.INITIAL

    # Addressing
    recipients_to: list[str]
    recipients_cc: list[str] = Field(default_factory=list)
    recipients_bcc: list[str] = Field(default_factory=list)

    subject: str
    body_plain: str
    body_html: Optional[str] = None

    # Metadata
    references: list[str] = Field(
        default_factory=list,
        description="Meeting IDs or previous email IDs this message is part of",
    )
    mode: EmailMode = EmailMode.DRAFT_ONLY

    graph_draft_id: Optional[str] = Field(
        None, description="Outlook draft message ID after creation via Graph API"
    )
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
