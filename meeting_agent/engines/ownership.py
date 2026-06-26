from __future__ import annotations

import logging

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.ownership import ActionOwnerModel
from meeting_agent.skills.owner_detection import OwnerDetectionSkill

logger = logging.getLogger(__name__)


class OwnershipEngine:
    """
    MODULE 4 — Resolve ownership for each extracted action item.

    For every action:
      1. Calls OwnerDetectionSkill
      2. Applies the result back to the ActionItem (assigned_to, assigned_to_email)
      3. Flags actions assigned to the primary user
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._skill = OwnerDetectionSkill(settings)

    def resolve(
        self,
        actions: list[ActionItem],
        context: MeetingContext,
    ) -> list[ActionOwnerModel]:
        participants = [
            {"name": p.name, "email": p.email or ""}
            for p in context.participants
        ]
        primary_user = self.settings.primary_user.name

        results: list[ActionOwnerModel] = []
        for action in actions:
            try:
                owner_model = self._skill.run(
                    action=action,
                    participants=participants,
                    primary_user=primary_user,
                )
                # Write resolved fields back to the action
                action.assigned_to = owner_model.resolved_owner or action.assigned_to
                action.assigned_to_email = owner_model.resolved_email or action.assigned_to_email
                results.append(owner_model)
                logger.debug(
                    "Action %s → owner=%s (confidence=%.2f, flagged_for_me=%s)",
                    action.action_id[:8],
                    owner_model.resolved_owner,
                    owner_model.confidence,
                    owner_model.flagged_for_sally,
                )
            except Exception as exc:
                logger.error("Ownership resolution failed for action %s: %s", action.action_id[:8], exc)

        return results
