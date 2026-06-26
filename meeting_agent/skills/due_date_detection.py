from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from dateutil import parser as dateutil_parser

from meeting_agent.models.action import ActionItem
from meeting_agent.skills.base import BaseSkill

# Deterministic relative-date patterns tried before LLM
_RELATIVE_MAP: dict[str, timedelta] = {
    "today": timedelta(days=0),
    "tomorrow": timedelta(days=1),
    "end of week": timedelta(days=4),
    "eow": timedelta(days=4),
    "end of month": timedelta(days=30),
    "next week": timedelta(days=7),
    "asap": timedelta(days=1),
    "urgent": timedelta(days=1),
}

_SYSTEM_PROMPT = """
You are a due-date extraction specialist.

Given an action statement and the meeting date, extract the due date if one is stated or implied.
Respond ONLY with a JSON object:
{
  "due_date_iso": "<ISO-8601 date or null>",
  "due_date_raw": "<original phrase or null>",
  "confidence": <0.0-1.0>
}
Never invent a due date that is not present or strongly implied.
"""


class DueDateDetectionSkill(BaseSkill):
    """Hybrid skill: deterministic date parsing → AI fallback."""

    def _build_messages(
        self,
        action: ActionItem,
        meeting_date: datetime,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"MEETING DATE: {meeting_date.date().isoformat()}\n"
                    f"ACTION: {action.raw_statement}"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> dict:
        return self._extract_json(raw)

    def run(self, action: ActionItem, meeting_date: datetime) -> Optional[datetime]:
        # 1. Deterministic: relative phrases
        statement_lower = action.raw_statement.lower()
        for phrase, delta in _RELATIVE_MAP.items():
            if phrase in statement_lower:
                return meeting_date + delta

        # 2. Deterministic: absolute date patterns (e.g. "by June 30")
        detected = self._try_parse_absolute(action.raw_statement, meeting_date)
        if detected:
            return detected

        # 3. AI fallback
        result = super().run(action=action, meeting_date=meeting_date)
        raw_iso = result.get("due_date_iso")
        if raw_iso:
            try:
                return dateutil_parser.parse(raw_iso)
            except Exception:
                return None
        return None

    @staticmethod
    def _try_parse_absolute(text: str, reference: datetime) -> Optional[datetime]:
        patterns = [
            r"\b(by|before|on|due)\s+([A-Z][a-z]+\s+\d{1,2}(?:,?\s*\d{4})?)\b",
            r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
            r"\b(\d{4}-\d{2}-\d{2})\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = m.group(m.lastindex)
                try:
                    parsed = dateutil_parser.parse(candidate, default=reference)
                    if parsed > reference:
                        return parsed
                except Exception:
                    continue
        return None
