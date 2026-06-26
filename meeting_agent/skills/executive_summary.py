from __future__ import annotations

from typing import Any

from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.task import Task
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are an executive summary writer.

Given a meeting context and a list of action items extracted from the meeting,
produce a concise executive summary suitable for sharing with stakeholders.

Structure:
1. Meeting overview (2-3 sentences)
2. Key decisions (bullet list)
3. Action items (bullet list with owner and due date)
4. Risks or blockers identified (bullet list, omit if none)
5. Next steps

Respond ONLY with a JSON object:
{
  "overview": "...",
  "key_decisions": ["...", "..."],
  "action_items_summary": ["Owner: task (due: date)", "..."],
  "risks": ["..."],
  "next_steps": ["..."],
  "full_text": "complete formatted summary as plain text"
}
"""


class ExecutiveSummarySkill(BaseSkill):
    """AI skill: generate a structured executive summary for a processed meeting."""

    def _build_messages(
        self,
        context: MeetingContext,
        tasks: list[Task],
    ) -> list[dict[str, str]]:
        tasks_text = "\n".join(
            f"- {t.description} | owner: {t.owner or 'TBD'} | due: {t.due_date.date() if t.due_date else 'TBD'}"
            for t in tasks
        )
        notes_excerpt = (context.facilitator_notes or "")[:3000]
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"MEETING: {context.title}\n"
                    f"DATE: {context.date.date()}\n"
                    f"ORGANIZER: {context.organizer.name}\n"
                    f"PARTICIPANTS: {', '.join(p.name for p in context.participants)}\n\n"
                    f"FACILITATOR NOTES (excerpt):\n{notes_excerpt}\n\n"
                    f"EXTRACTED ACTIONS:\n{tasks_text or 'None'}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict[str, Any]:
        return self._extract_json(raw)

    def run(self, context: MeetingContext, tasks: list[Task]) -> dict[str, Any]:
        return super().run(context=context, tasks=tasks)
