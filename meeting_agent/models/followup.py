from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FollowUpStepType(str, Enum):
    DRAFT_EMAIL = "draft_email"
    SEND_EMAIL = "send_email"
    CREATE_MEETING = "create_meeting"
    WAIT_FOR_RESPONSE = "wait_for_response"
    ESCALATE = "escalate"
    UPDATE_DOCUMENTATION = "update_documentation"
    REQUEST_APPROVAL = "request_approval"
    SET_REMINDER = "set_reminder"
    MARK_COMPLETE = "mark_complete"


class FollowUpStep(BaseModel):
    step_number: int
    step_type: FollowUpStepType
    description: str
    requires_approval: bool = False
    trigger_condition: Optional[str] = Field(
        None,
        description="Condition that triggers this step (e.g. 'no response after 5 days')",
    )


class FollowUpPlan(BaseModel):
    """Sequence of follow-up steps for a single action item."""

    action_id: str
    steps: list[FollowUpStep]
    email_required: bool = False
    meeting_required: bool = False
    documentation_required: bool = False
    approval_required: bool = False
    escalation_required: bool = False
    reminder_required: bool = False
    rationale: str = Field(description="AI explanation for why these steps were chosen")
