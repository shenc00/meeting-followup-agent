from __future__ import annotations

from typing import Any

from meeting_agent.models.action import ActionItem
from meeting_agent.models.followup import FollowUpPlan, FollowUpStep, FollowUpStepType
from meeting_agent.skills.base import BaseSkill

_SYSTEM_PROMPT = """
You are a follow-up planning specialist.

Given an action item, produce a structured follow-up plan: the ordered sequence of steps
required to drive this action to closure.

Respond ONLY with a JSON object:
{
  "email_required": bool,
  "meeting_required": bool,
  "documentation_required": bool,
  "approval_required": bool,
  "escalation_required": bool,
  "reminder_required": bool,
  "rationale": "brief explanation",
  "steps": [
    {
      "step_number": 1,
      "step_type": "draft_email | send_email | create_meeting | wait_for_response | escalate | update_documentation | request_approval | set_reminder | mark_complete",
      "description": "...",
      "requires_approval": bool,
      "trigger_condition": "... or null"
    }
  ]
}

Valid step_type values:
draft_email, send_email, create_meeting, wait_for_response, escalate,
update_documentation, request_approval, set_reminder, mark_complete
"""


class FollowUpPlanningSkill(BaseSkill):
    """AI skill: determine the follow-up plan for a single action item."""

    def _build_messages(self, action: ActionItem) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ACTION: {action.task_description}\n"
                    f"OWNER: {action.assigned_to or 'unknown'}\n"
                    f"CLASSIFICATION: {action.classification.value}\n"
                    f"PRIORITY: {action.priority.value}\n"
                    f"EVIDENCE: {action.raw_statement}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict[str, Any]:
        return self._extract_json(raw)

    def run(self, action: ActionItem) -> FollowUpPlan:
        result = super().run(action=action)
        steps = [
            FollowUpStep(
                step_number=s["step_number"],
                step_type=FollowUpStepType(s["step_type"]),
                description=s["description"],
                requires_approval=s.get("requires_approval", False),
                trigger_condition=s.get("trigger_condition"),
            )
            for s in result.get("steps", [])
        ]
        return FollowUpPlan(
            action_id=action.action_id,
            steps=steps,
            email_required=result.get("email_required", False),
            meeting_required=result.get("meeting_required", False),
            documentation_required=result.get("documentation_required", False),
            approval_required=result.get("approval_required", False),
            escalation_required=result.get("escalation_required", False),
            reminder_required=result.get("reminder_required", False),
            rationale=result.get("rationale", ""),
        )
