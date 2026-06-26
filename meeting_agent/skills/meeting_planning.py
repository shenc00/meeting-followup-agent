from __future__ import annotations

from typing import Any

from meeting_agent.models.action import ActionItem
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.scheduling import MeetingRequest, SchedulingMode
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are a meeting planning specialist.

Given an action item requiring a follow-up meeting, produce a structured meeting request.

Respond ONLY with a JSON object:
{
  "subject": "...",
  "objective": "...",
  "estimated_duration_minutes": 30,
  "agenda": ["agenda item 1", "agenda item 2"],
  "required_attendees": ["email1", "email2"],
  "optional_attendees": []
}

Rules:
- Never add attendees not present in the participants list
- Duration should be 30 minutes unless the objective clearly requires more
- Agenda should be specific, not generic
"""


class MeetingPlanningSkill(BaseSkill):
    """AI skill: produce a structured meeting request for a follow-up action."""

    def _build_messages(
        self,
        action: ActionItem,
        context: MeetingContext,
    ) -> list[dict[str, str]]:
        participants_text = "\n".join(
            f"- {p.name} ({p.email or 'no email'})"
            for p in context.participants
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ORIGINATING MEETING: {context.title}\n"
                    f"PARTICIPANTS:\n{participants_text}\n\n"
                    f"ACTION REQUIRING MEETING: {action.task_description}\n"
                    f"EVIDENCE: {action.raw_statement}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict[str, Any]:
        return self._extract_json(raw)

    def run(
        self,
        action: ActionItem,
        context: MeetingContext,
        mode: SchedulingMode = SchedulingMode.DRAFT_ONLY,
    ) -> MeetingRequest:
        result = super().run(action=action, context=context)
        return MeetingRequest(
            action_id=action.action_id,
            meeting_id=context.meeting_id,
            subject=result.get("subject", f"Follow-up: {action.task_description[:60]}"),
            objective=result.get("objective", action.task_description),
            estimated_duration_minutes=int(result.get("estimated_duration_minutes", 30)),
            agenda=result.get("agenda", []),
            required_attendees=result.get("required_attendees", []),
            optional_attendees=result.get("optional_attendees", []),
            mode=mode,
        )
