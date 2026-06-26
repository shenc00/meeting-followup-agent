from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MeetingSource(str, Enum):
    TEAMS = "teams"
    OUTLOOK = "outlook"
    MANUAL = "manual"


class MeetingParticipant(BaseModel):
    name: str
    email: Optional[str] = None
    role: Optional[str] = None  # organizer | presenter | attendee


class MeetingContext(BaseModel):
    """Aggregated context for a single meeting, built by MeetingIngestionEngine."""

    meeting_id: str = Field(description="Stable unique identifier (Teams/Graph event ID)")
    title: str
    date: datetime
    organizer: MeetingParticipant
    participants: list[MeetingParticipant] = Field(default_factory=list)
    source: MeetingSource = MeetingSource.TEAMS

    # Raw content — priority order mirrors the spec
    facilitator_notes: Optional[str] = None
    transcript: Optional[str] = None
    chat_messages: Optional[str] = None
    description: Optional[str] = None
    attachments: list[str] = Field(default_factory=list, description="File paths or URLs")
    shared_links: list[str] = Field(default_factory=list)

    # Derived / normalised body used by extraction engines
    normalised_body: Optional[str] = None

    processed_at: Optional[datetime] = None
    processing_notes: list[str] = Field(default_factory=list)
