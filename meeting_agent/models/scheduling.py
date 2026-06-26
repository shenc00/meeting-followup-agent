from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SchedulingMode(str, Enum):
    DRAFT_ONLY = "draft"
    DRAFT_AND_APPROVAL = "approval"
    AUTO_SCHEDULE = "auto_schedule"


class MeetingRequest(BaseModel):
    """A meeting invitation to be created via the Scheduling Engine."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str
    meeting_id: str = Field(description="Originating meeting FK")

    subject: str
    objective: str
    estimated_duration_minutes: int = 30
    agenda: list[str] = Field(default_factory=list)
    required_attendees: list[str]
    optional_attendees: list[str] = Field(default_factory=list)
    proposed_dates: list[datetime] = Field(default_factory=list)

    mode: SchedulingMode = SchedulingMode.DRAFT_ONLY
    graph_event_id: Optional[str] = Field(
        None, description="Graph calendar event ID after creation"
    )
    teams_join_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
