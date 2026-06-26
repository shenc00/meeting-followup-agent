from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from meeting_agent.models.action import ActionClassification, ActionPriority, ActionStatus


class Task(BaseModel):
    """
    Persistent work item stored in the action repository.

    Combines the original ActionItem fields with lifecycle tracking so that
    one record is maintained from extraction through to closure.
    """

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    action_id: str = Field(description="FK → ActionItem.action_id")
    meeting_id: str

    description: str
    raw_evidence: str = Field(description="Verbatim source statement")

    owner: Optional[str] = None
    owner_email: Optional[str] = None

    due_date: Optional[datetime] = None
    classification: ActionClassification = ActionClassification.FOLLOW_UP_ACTION
    priority: ActionPriority = ActionPriority.MEDIUM
    status: ActionStatus = ActionStatus.OPEN

    # Linked artefacts
    related_email_ids: list[str] = Field(default_factory=list)
    related_meeting_request_ids: list[str] = Field(default_factory=list)

    # Lifecycle timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    last_reminder_sent_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None

    # Governance
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    notes: list[str] = Field(default_factory=list, description="Free-text progress notes")

    def mark_complete(self) -> None:
        self.status = ActionStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def is_overdue(self) -> bool:
        if self.due_date is None or self.status == ActionStatus.COMPLETED:
            return False
        return datetime.utcnow() > self.due_date
