from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionClassification(str, Enum):
    EMAIL_REQUIRED = "email_required"
    MEETING_REQUIRED = "meeting_required"
    INFORMATION_REQUEST = "information_request"
    DOCUMENTATION_UPDATE = "documentation_update"
    REPORT_GENERATION = "report_generation"
    DASHBOARD_CHANGE = "dashboard_change"
    DATA_PRODUCT_WORK = "data_product_work"
    FOLLOW_UP_ACTION = "follow_up_action"


class ActionStatus(str, Enum):
    OPEN = "open"
    DRAFTED = "drafted"
    WAITING_RESPONSE = "waiting_response"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActionPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionItem(BaseModel):
    """A single extracted action item with full traceability back to source meeting."""

    action_id: str = Field(default_factory=lambda: str(uuid4()))
    meeting_id: str = Field(description="FK → MeetingContext.meeting_id")

    # Core fields
    task_description: str
    raw_statement: str = Field(description="Verbatim text from the meeting source")
    source_field: str = Field(
        description="Which source field the statement came from: notes | transcript | chat"
    )

    # Ownership
    assigned_to: Optional[str] = None
    assigned_to_email: Optional[str] = None

    # Scheduling
    due_date: Optional[datetime] = None
    due_date_raw: Optional[str] = Field(
        None, description="Original due-date text before parsing"
    )

    # Classification
    classification: ActionClassification = ActionClassification.FOLLOW_UP_ACTION
    priority: ActionPriority = ActionPriority.MEDIUM
    status: ActionStatus = ActionStatus.OPEN

    # AI confidence
    extraction_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Confidence score from the extraction skill"
    )

    # Linked artefacts
    related_email_ids: list[str] = Field(default_factory=list)
    related_meeting_request_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
