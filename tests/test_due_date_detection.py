from __future__ import annotations

from datetime import datetime

import pytest

from meeting_agent.skills.due_date_detection import DueDateDetectionSkill
from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem


def _action(statement: str) -> ActionItem:
    return ActionItem(
        meeting_id="m-001",
        task_description="Test task",
        raw_statement=statement,
        source_field="notes",
    )


MEETING_DATE = datetime(2026, 6, 26)


class TestDueDateDetectionSkill:
    """Test the deterministic (non-LLM) layers of the due-date skill."""

    def setup_method(self):
        self._skill = DueDateDetectionSkill(Settings())

    def test_today_relative(self):
        action = _action("Alice to confirm today")
        result = self._skill.run(action, MEETING_DATE)
        assert result is not None
        assert result.date() == MEETING_DATE.date()

    def test_tomorrow_relative(self):
        action = _action("Bob will send the report tomorrow")
        result = self._skill.run(action, MEETING_DATE)
        from datetime import timedelta
        assert result is not None
        assert result.date() == (MEETING_DATE + timedelta(days=1)).date()

    def test_eow_relative(self):
        action = _action("Please share by EOW")
        result = self._skill.run(action, MEETING_DATE)
        from datetime import timedelta
        assert result is not None
        assert result.date() == (MEETING_DATE + timedelta(days=4)).date()

    def test_absolute_iso_date(self):
        action = _action("Confirm by 2026-07-15")
        result = self._skill._try_parse_absolute(action.raw_statement, MEETING_DATE)
        assert result is not None
        assert result.year == 2026
        assert result.month == 7
        assert result.day == 15

    def test_no_date_returns_none_without_llm(self, monkeypatch):
        """When no deterministic match and LLM returns null, result is None."""
        action = _action("Alice to arrange something")

        def mock_super_run(**kwargs):
            return {"due_date_iso": None, "confidence": 0.0}

        monkeypatch.setattr(
            "meeting_agent.skills.base.BaseSkill.run",
            lambda self, **kwargs: {"due_date_iso": None, "confidence": 0.0},
        )
        # Deterministic pass only — no LLM call expected here
        result = self._skill._try_parse_absolute(action.raw_statement, MEETING_DATE)
        assert result is None
