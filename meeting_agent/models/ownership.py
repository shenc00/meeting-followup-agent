from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OwnershipType(str, Enum):
    ASSIGNED_TO_ME = "assigned_to_me"
    ASSIGNED_TO_OTHERS = "assigned_to_others"
    SHARED = "shared"
    UNKNOWN = "unknown"


class ActionOwnerModel(BaseModel):
    """Ownership resolution result produced by OwnershipEngine."""

    action_id: str
    resolved_owner: Optional[str] = None
    resolved_email: Optional[str] = None
    ownership_type: OwnershipType = OwnershipType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = Field(description="Verbatim statement that indicates ownership")
    co_owners: list[str] = Field(default_factory=list)
    flagged_for_sally: bool = Field(
        default=False,
        description="True when the primary user is the assigned or co-owner",
    )
