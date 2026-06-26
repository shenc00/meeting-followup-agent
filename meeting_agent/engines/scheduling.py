from __future__ import annotations

import logging

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem
from meeting_agent.models.followup import FollowUpPlan
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.scheduling import MeetingRequest, SchedulingMode
from meeting_agent.skills.meeting_planning import MeetingPlanningSkill

logger = logging.getLogger(__name__)


class SchedulingEngine:
    """
    MODULE 7 — Create calendar invitations when a follow-up meeting is required.

    Modes (configurable):
      draft        — produce MeetingRequest object only
      approval     — create calendar draft, flag for user approval
      auto_schedule — immediately create and send calendar invitation via Graph
    """

    def __init__(self, settings: Settings, graph_client=None) -> None:
        self.settings = settings
        self._skill = MeetingPlanningSkill(settings)
        self._graph = graph_client
        self._mode = SchedulingMode(settings.scheduling_mode)

    def schedule(
        self,
        actions: list[ActionItem],
        plans: list[FollowUpPlan],
        context: MeetingContext,
    ) -> list[MeetingRequest]:
        plan_map = {p.action_id: p for p in plans}
        requests: list[MeetingRequest] = []

        for action in actions:
            plan = plan_map.get(action.action_id)
            if plan is None or not plan.meeting_required:
                continue

            try:
                request = self._skill.run(
                    action=action, context=context, mode=self._mode
                )
                self._handle_request(request)
                action.related_meeting_request_ids.append(request.request_id)
                requests.append(request)
                logger.info(
                    "Meeting request created for action %s — mode=%s",
                    action.action_id[:8],
                    self._mode.value,
                )
            except Exception as exc:
                logger.error(
                    "Scheduling failed for action %s: %s",
                    action.action_id[:8],
                    exc,
                )

        return requests

    def _handle_request(self, request: MeetingRequest) -> None:
        if self._graph is None:
            return

        if self._mode == SchedulingMode.AUTO_SCHEDULE:
            event_id, join_url = self._graph.create_calendar_event(request)
            request.graph_event_id = event_id
            request.teams_join_url = join_url
            logger.info("Calendar event created: %s", event_id)
        elif self._mode == SchedulingMode.DRAFT_AND_APPROVAL:
            logger.info("Meeting request prepared — awaiting user approval")
