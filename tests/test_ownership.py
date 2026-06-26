from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from meeting_agent.config import Settings
from meeting_agent.engines.ownership import OwnershipEngine
from meeting_agent.models.action import ActionItem
from meeting_agent.models.meeting import MeetingContext, MeetingParticipant, MeetingSource
from meeting_agent.models.ownership import ActionOwnerModel, OwnershipType


def _make_action(assigned_to: str | None = None) -> ActionItem:
    return ActionItem(
        meeting_id="m-001",
        task_description="Review the APM impact",
        raw_statement="Sally to review APM impact with Gaten",
        source_field="notes",
        assigned_to=assigned_to,
        extraction_confidence=0.9,
    )


def _make_context() -> MeetingContext:
    return MeetingContext(
        meeting_id="m-001",
        title="APM Review",
        date=datetime(2026, 6, 26),
        organizer=MeetingParticipant(name="Alice", email="alice@example.com"),
        participants=[
            MeetingParticipant(name="Sally", email="sally@example.com"),
            MeetingParticipant(name="Gaten", email="gaten@example.com"),
        ],
        source=MeetingSource.TEAMS,
    )


class TestOwnershipEngine:
    def test_resolves_primary_user_as_flagged(self):
        engine = OwnershipEngine(Settings())
        action = _make_action()
        context = _make_context()

        mock_model = ActionOwnerModel(
            action_id=action.action_id,
            resolved_owner="Sally",
            resolved_email="sally@example.com",
            ownership_type=OwnershipType.ASSIGNED_TO_ME,
            confidence=0.95,
            evidence="Sally to review APM impact with Gaten",
            flagged_for_sally=True,
        )

        with patch.object(engine._skill, "run", return_value=mock_model):
            results = engine.resolve([action], context)

        assert len(results) == 1
        assert results[0].flagged_for_sally is True
        assert action.assigned_to == "Sally"
        assert action.assigned_to_email == "sally@example.com"

    def test_action_updated_with_resolved_owner(self):
        engine = OwnershipEngine(Settings())
        action = _make_action()
        context = _make_context()

        mock_model = ActionOwnerModel(
            action_id=action.action_id,
            resolved_owner="Gaten",
            resolved_email="gaten@example.com",
            ownership_type=OwnershipType.ASSIGNED_TO_OTHERS,
            confidence=0.8,
            evidence="Gaten to provide data",
            flagged_for_sally=False,
        )

        with patch.object(engine._skill, "run", return_value=mock_model):
            results = engine.resolve([action], context)

        assert action.assigned_to == "Gaten"
        assert results[0].ownership_type == OwnershipType.ASSIGNED_TO_OTHERS

    def test_continues_on_skill_error(self):
        engine = OwnershipEngine(Settings())
        action = _make_action()
        context = _make_context()

        with patch.object(engine._skill, "run", side_effect=RuntimeError("LLM failure")):
            results = engine.resolve([action], context)

        # Should not raise; returns empty results gracefully
        assert results == []
