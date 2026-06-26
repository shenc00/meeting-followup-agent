from __future__ import annotations

import logging

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem
from meeting_agent.models.followup import FollowUpPlan
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.skills.due_date_detection import DueDateDetectionSkill
from meeting_agent.skills.followup_planning import FollowUpPlanningSkill

logger = logging.getLogger(__name__)


class FollowUpEngine:
    """
    MODULE 5 — Determine next steps for every action item.

    For each action:
      1. Resolve the due date (DueDateDetectionSkill)
      2. Build a follow-up plan (FollowUpPlanningSkill)
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._date_skill = DueDateDetectionSkill(settings)
        self._plan_skill = FollowUpPlanningSkill(settings)

    def build_plans(
        self,
        actions: list[ActionItem],
        context: MeetingContext,
    ) -> list[FollowUpPlan]:
        plans: list[FollowUpPlan] = []
        for action in actions:
            # Resolve due date if not already set
            if action.due_date is None:
                try:
                    action.due_date = self._date_skill.run(
                        action=action, meeting_date=context.date
                    )
                except Exception as exc:
                    logger.warning("Due-date detection failed for %s: %s", action.action_id[:8], exc)

            # Build follow-up plan
            try:
                plan = self._plan_skill.run(action=action)
                plans.append(plan)
                logger.debug(
                    "Follow-up plan for %s: %d step(s), email=%s, meeting=%s",
                    action.action_id[:8],
                    len(plan.steps),
                    plan.email_required,
                    plan.meeting_required,
                )
            except Exception as exc:
                logger.error("Follow-up planning failed for %s: %s", action.action_id[:8], exc)

        return plans
