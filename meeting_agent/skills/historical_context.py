from __future__ import annotations

from typing import Any

from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.task import Task
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are a historical context analyst for meeting action tracking.

Given the current meeting context and a list of historically open actions,
identify connections:
- Repeated topics
- Previously assigned actions that are still open
- Missed commitments
- Relevant historical decisions

Respond ONLY with a JSON array. Each element:
{
  "current_description": "current action or topic",
  "historical_task_id": "task ID from history or null",
  "connection_type": "repeated_topic | open_action | missed_commitment | related_decision",
  "explanation": "brief explanation"
}

Return an empty array if no connections exist.
"""


class HistoricalContextSkill(BaseSkill):
    """AI skill: connect current meeting actions to historical open tasks."""

    def _build_messages(
        self,
        context: MeetingContext,
        open_tasks: list[Task],
    ) -> list[dict[str, str]]:
        history_text = "\n".join(
            f"- [{t.task_id}] {t.description} (owner: {t.owner}, status: {t.status.value})"
            for t in open_tasks[:50]  # cap at 50 to stay within token budget
        )
        body_parts = filter(None, [context.facilitator_notes, context.transcript])
        current_body = "\n".join(body_parts)[:3000]
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"CURRENT MEETING: {context.title} on {context.date.date()}\n\n"
                    f"CURRENT CONTENT (excerpt):\n{current_body}\n\n"
                    f"HISTORICAL OPEN TASKS:\n{history_text}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> list[dict[str, Any]]:
        return self._extract_json(raw)

    def run(
        self,
        context: MeetingContext,
        open_tasks: list[Task],
    ) -> list[dict[str, Any]]:
        if not open_tasks:
            return []
        return super().run(context=context, open_tasks=open_tasks)
