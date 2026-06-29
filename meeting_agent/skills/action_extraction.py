from __future__ import annotations

import re
from typing import Any

from meeting_agent.models.action import ActionClassification, ActionItem, ActionPriority
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.skills.base import BaseSkill

# Deterministic trigger patterns — checked before calling the LLM
_TRIGGER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bto\s+(confirm|review|schedule|send|provide|investigate|follow up|update|draft|escalate|share|check|validate|complete)\b", re.IGNORECASE),
    re.compile(r"\bwill\s+(confirm|review|schedule|send|provide|investigate|update|draft|escalate|share|check|validate|complete)\b", re.IGNORECASE),
    re.compile(r"\b(need to|needs to|action:)\b", re.IGNORECASE),
    re.compile(r"\b(follow up with|schedule a|arrange a|set up|book a)\b", re.IGNORECASE),
    re.compile(r"\b(AI|AP)\s+required\b", re.IGNORECASE),
]

_SYSTEM_PROMPT = """
You are a meeting assistant. Extract every action item from the meeting notes.

An action item is ANY sentence where someone is responsible for doing something, including:
- "X planned to Y"  →  task for X
- "X will Y"  →  task for X
- "X needs to Y" or "X discussed the need to Y"
- Items under Follow-up tasks, Action items, or Next steps sections
- Bullet points like "X - do Y" or "X: do Y"

Return ONLY a valid JSON array. No explanation, no markdown fences, just the array.

Example output for notes containing "Terence planned to find out from Sandeep about governance":
[
  {
    "task_description": "Find out from Sandeep who approves new data products",
    "assigned_to": "Terence",
    "priority": "medium",
    "raw_statement": "Terence planned to find out from Sandeep who is responsible",
    "classification": "follow_up_action",
    "extraction_confidence": 0.9,
    "due_date_raw": null,
    "source_field": "notes"
  }
]

If there are truly no action items, output exactly: []
"""


class ActionExtractionSkill(BaseSkill):
    """AI skill: extract structured action items from meeting text."""

    def _build_messages(self, context: MeetingContext) -> list[dict[str, str]]:
        body = self._build_body(context)
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"MEETING: {context.title}\nDATE: {context.date}\n\n{body}"},
        ]

    def _parse_response(self, raw: str) -> list[dict[str, Any]]:
        return self._extract_json(raw)

    def run(self, context: MeetingContext) -> list[ActionItem]:
        # Fast deterministic pre-filter on each sentence
        candidate_sentences = self._candidate_sentences(context)
        if not candidate_sentences and not context.normalised_body:
            return []

        raw_items: list[dict[str, Any]] = super().run(context=context)
        return [
            ActionItem(
                meeting_id=context.meeting_id,
                task_description=item.get("task_description", ""),
                raw_statement=item.get("raw_statement", ""),
                source_field=item.get("source_field", "notes"),
                assigned_to=item.get("assigned_to"),
                due_date_raw=item.get("due_date_raw"),
                classification=ActionClassification(
                    item.get("classification", "follow_up_action")
                ),
                priority=ActionPriority(item.get("priority", "medium")),
                extraction_confidence=float(item.get("extraction_confidence", 0.8)),
            )
            for item in raw_items
        ]

    @staticmethod
    def _build_body(context: MeetingContext) -> str:
        parts: list[str] = []
        if context.facilitator_notes:
            parts.append(f"=== FACILITATOR NOTES ===\n{context.facilitator_notes}")
        if context.transcript:
            parts.append(f"=== TRANSCRIPT ===\n{context.transcript}")
        if context.chat_messages:
            parts.append(f"=== CHAT ===\n{context.chat_messages}")
        return "\n\n".join(parts) or "(no content)"

    @staticmethod
    def _candidate_sentences(context: MeetingContext) -> list[str]:
        body = " ".join(
            filter(None, [context.facilitator_notes, context.transcript, context.chat_messages])
        )
        return [
            s.strip()
            for s in re.split(r"[.\n]", body)
            if any(p.search(s) for p in _TRIGGER_PATTERNS)
        ]
