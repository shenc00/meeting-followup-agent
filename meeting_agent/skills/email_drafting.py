from __future__ import annotations

from typing import Any

from meeting_agent.models.action import ActionItem
from meeting_agent.models.email import DraftEmailPackage, EmailMode, EmailType
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are an expert business email writer acting as an executive assistant.

Given an action item and meeting context, draft a complete, professional business email.

Rules:
- Be concise and action-oriented
- Do not invent facts — reference only what is in the provided context
- Generate a plain-text body AND an equivalent HTML body
- Choose recipients based on the action owner and meeting participants

Respond ONLY with a JSON object:
{
  "recipients_to": ["email1", "email2"],
  "recipients_cc": [],
  "subject": "...",
  "body_plain": "...",
  "body_html": "<p>...</p>"
}
"""

_REMINDER_SUFFIX = "\n\nThis is a reminder regarding the action above, which remains open."
_ESCALATION_SUFFIX = "\n\nThis action has been open for an extended period and requires escalation."


class EmailDraftingSkill(BaseSkill):
    """AI skill: draft a complete Outlook email for an action item."""

    def _build_messages(
        self,
        action: ActionItem,
        context: MeetingContext,
        email_type: EmailType = EmailType.INITIAL,
    ) -> list[dict[str, str]]:
        suffix = {
            EmailType.REMINDER: _REMINDER_SUFFIX,
            EmailType.ESCALATION: _ESCALATION_SUFFIX,
        }.get(email_type, "")
        participants_text = "\n".join(
            f"- {p.name} ({p.email or 'no email'})"
            for p in context.participants
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"MEETING: {context.title} on {context.date.date()}\n"
                    f"PARTICIPANTS:\n{participants_text}\n\n"
                    f"ACTION: {action.task_description}\n"
                    f"OWNER: {action.assigned_to or 'TBD'}\n"
                    f"EVIDENCE: {action.raw_statement}"
                    f"{suffix}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict[str, Any]:
        return self._extract_json(raw)

    def run(
        self,
        action: ActionItem,
        context: MeetingContext,
        email_type: EmailType = EmailType.INITIAL,
        mode: EmailMode = EmailMode.DRAFT_ONLY,
    ) -> DraftEmailPackage:
        result = super().run(action=action, context=context, email_type=email_type)
        return DraftEmailPackage(
            action_id=action.action_id,
            meeting_id=context.meeting_id,
            email_type=email_type,
            recipients_to=result.get("recipients_to", []),
            recipients_cc=result.get("recipients_cc", []),
            subject=result.get("subject", f"Follow-up: {action.task_description[:60]}"),
            body_plain=result.get("body_plain", ""),
            body_html=result.get("body_html"),
            references=[context.meeting_id],
            mode=mode,
        )
