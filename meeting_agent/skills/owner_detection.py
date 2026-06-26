from __future__ import annotations

from typing import Any

from meeting_agent.models.action import ActionItem
from meeting_agent.models.ownership import ActionOwnerModel, OwnershipType
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are an ownership resolution expert.

Given a list of meeting participants and an action statement, determine:
- resolved_owner: the person primarily responsible (use exact name from participants list)
- resolved_email: their email if known
- ownership_type: assigned_to_me | assigned_to_others | shared | unknown
- confidence: 0.0–1.0
- evidence: verbatim phrase showing ownership
- co_owners: list of additional owners (names only)
- flagged_for_sally: true if the primary user "Sally" is the owner or co-owner

Respond ONLY with a single JSON object with exactly these fields.
Never invent names not present in the participants list.
"""


class OwnerDetectionSkill(BaseSkill):
    """AI skill: resolve action ownership from meeting participants and statement."""

    def _build_messages(
        self,
        action: ActionItem,
        participants: list[dict[str, str]],
        primary_user: str,
    ) -> list[dict[str, str]]:
        participants_text = "\n".join(
            f"- {p.get('name')} ({p.get('email', 'email unknown')})"
            for p in participants
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"PRIMARY USER: {primary_user}\n"
                    f"PARTICIPANTS:\n{participants_text}\n\n"
                    f"ACTION STATEMENT:\n{action.raw_statement}\n\n"
                    f"TASK: {action.task_description}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict[str, Any]:
        return self._extract_json(raw)

    def run(
        self,
        action: ActionItem,
        participants: list[dict[str, str]],
        primary_user: str,
    ) -> ActionOwnerModel:
        result: dict[str, Any] = super().run(
            action=action,
            participants=participants,
            primary_user=primary_user,
        )
        return ActionOwnerModel(
            action_id=action.action_id,
            resolved_owner=result.get("resolved_owner"),
            resolved_email=result.get("resolved_email"),
            ownership_type=OwnershipType(result.get("ownership_type", "unknown")),
            confidence=float(result.get("confidence", 0.0)),
            evidence=result.get("evidence", action.raw_statement),
            co_owners=result.get("co_owners", []),
            flagged_for_sally=bool(result.get("flagged_for_sally", False)),
        )
