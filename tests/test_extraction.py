from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from meeting_agent.config import Settings
from meeting_agent.engines.extraction import ActionExtractionEngine
from meeting_agent.models.action import ActionItem, ActionClassification
from meeting_agent.models.meeting import MeetingContext, MeetingParticipant, MeetingSource


def _make_context(notes: str = "") -> MeetingContext:
    ctx = MeetingContext(
        meeting_id="test-meeting-001",
        title="Test Meeting",
        date=datetime(2026, 6, 26, 10, 0),
        organizer=MeetingParticipant(name="Alice", email="alice@example.com"),
        participants=[
            MeetingParticipant(name="Alice", email="alice@example.com"),
            MeetingParticipant(name="Bob", email="bob@example.com"),
        ],
        source=MeetingSource.TEAMS,
        facilitator_notes=notes,
    )
    ctx.normalised_body = notes
    return ctx


def _make_settings() -> Settings:
    return Settings()


class TestActionExtractionEngine:
    def test_returns_empty_when_no_body(self):
        engine = ActionExtractionEngine(_make_settings())
        ctx = _make_context("")
        ctx.normalised_body = None
        result = engine.extract(ctx)
        assert result == []

    def test_deduplicates_identical_descriptions(self):
        """Two actions with the same description should appear only once."""
        engine = ActionExtractionEngine(_make_settings())

        mock_actions = [
            ActionItem(
                meeting_id="test-meeting-001",
                task_description="Send the report",
                raw_statement="Alice to send the report",
                source_field="notes",
                extraction_confidence=0.9,
            ),
            ActionItem(
                meeting_id="test-meeting-001",
                task_description="Send the report",  # duplicate
                raw_statement="Alice will send the report by Friday",
                source_field="notes",
                extraction_confidence=0.85,
            ),
        ]

        with patch.object(engine._skill, "run", return_value=mock_actions):
            ctx = _make_context("Alice to send the report")
            result = engine.extract(ctx)

        assert len(result) == 1

    def test_filters_low_confidence_actions(self):
        """Actions below the confidence threshold should be dropped."""
        engine = ActionExtractionEngine(_make_settings())

        mock_actions = [
            ActionItem(
                meeting_id="test-meeting-001",
                task_description="High confidence action",
                raw_statement="Bob to confirm by EOW",
                source_field="notes",
                extraction_confidence=0.9,
            ),
            ActionItem(
                meeting_id="test-meeting-001",
                task_description="Low confidence action",
                raw_statement="maybe something",
                source_field="notes",
                extraction_confidence=0.2,  # below threshold
            ),
        ]

        with patch.object(engine._skill, "run", return_value=mock_actions):
            ctx = _make_context("Bob to confirm by EOW")
            result = engine.extract(ctx)

        assert len(result) == 1
        assert result[0].task_description == "High confidence action"

    def test_classification_preserved(self):
        engine = ActionExtractionEngine(_make_settings())
        mock_actions = [
            ActionItem(
                meeting_id="test-meeting-001",
                task_description="Send project update email",
                raw_statement="Alice to send the project update",
                source_field="notes",
                classification=ActionClassification.EMAIL_REQUIRED,
                extraction_confidence=0.95,
            )
        ]
        with patch.object(engine._skill, "run", return_value=mock_actions):
            ctx = _make_context("Alice to send the project update")
            result = engine.extract(ctx)

        assert result[0].classification == ActionClassification.EMAIL_REQUIRED
