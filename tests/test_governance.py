from __future__ import annotations

from datetime import datetime

import pytest

from meeting_agent.engines.governance import GovernanceEngine
from meeting_agent.models.action import ActionItem, ActionClassification
from meeting_agent.models.email import DraftEmailPackage, EmailMode
from meeting_agent.models.meeting import MeetingContext, MeetingParticipant, MeetingSource
from meeting_agent.models.scheduling import MeetingRequest, SchedulingMode


def _context() -> MeetingContext:
    return MeetingContext(
        meeting_id="m-001",
        title="Test Meeting",
        date=datetime(2026, 6, 26),
        organizer=MeetingParticipant(name="Alice", email="alice@example.com"),
        participants=[
            MeetingParticipant(name="Alice", email="alice@example.com"),
            MeetingParticipant(name="Bob", email="bob@example.com"),
        ],
        source=MeetingSource.TEAMS,
    )


class TestGovernanceEngine:
    # ── Action validation ──────────────────────────────────────────────────────

    def test_valid_action_passes(self):
        engine = GovernanceEngine()
        action = ActionItem(
            meeting_id="m-001",
            task_description="Send project update",
            raw_statement="Alice to send project update by end of week",
            source_field="notes",
            assigned_to="Alice",
            due_date=datetime(2026, 6, 30),
            extraction_confidence=0.9,
        )
        result = engine.validate_action(action, _context())
        assert result.passed

    def test_missing_evidence_fails(self):
        engine = GovernanceEngine()
        action = ActionItem(
            meeting_id="m-001",
            task_description="Send update",
            raw_statement="   ",  # too short
            source_field="notes",
            extraction_confidence=0.9,
        )
        result = engine.validate_action(action, _context())
        assert not result.passed
        assert any("evidence" in v for v in result.violations)

    def test_past_due_date_fails(self):
        engine = GovernanceEngine()
        action = ActionItem(
            meeting_id="m-001",
            task_description="Complete review",
            raw_statement="Bob to complete review by January",
            source_field="notes",
            due_date=datetime(2026, 1, 1),  # before meeting date
            extraction_confidence=0.9,
        )
        result = engine.validate_action(action, _context())
        assert not result.passed
        assert any("due date" in v for v in result.violations)

    def test_unknown_owner_produces_warning(self):
        engine = GovernanceEngine()
        action = ActionItem(
            meeting_id="m-001",
            task_description="Update slides",
            raw_statement="Charlie to update the slides",
            source_field="notes",
            assigned_to="Charlie",  # not in participant list
            due_date=datetime(2026, 7, 1),
            extraction_confidence=0.9,
        )
        result = engine.validate_action(action, _context())
        assert result.passed  # warnings don't block
        assert any("not in the participant list" in w for w in result.warnings)

    # ── Email validation ───────────────────────────────────────────────────────

    def test_valid_email_passes(self):
        engine = GovernanceEngine()
        draft = DraftEmailPackage(
            action_id="a-001",
            meeting_id="m-001",
            recipients_to=["bob@example.com"],
            subject="Follow-up: project update",
            body_plain="Hi Bob, please see the action below.",
            mode=EmailMode.DRAFT_ONLY,
        )
        result = engine.validate_email(draft)
        assert result.passed

    def test_invalid_recipient_fails(self):
        engine = GovernanceEngine()
        draft = DraftEmailPackage(
            action_id="a-001",
            meeting_id="m-001",
            recipients_to=["not-an-email"],
            subject="Test",
            body_plain="Body",
            mode=EmailMode.DRAFT_ONLY,
        )
        result = engine.validate_email(draft)
        assert not result.passed

    def test_empty_recipients_fails(self):
        engine = GovernanceEngine()
        draft = DraftEmailPackage(
            action_id="a-001",
            meeting_id="m-001",
            recipients_to=[],
            subject="Test",
            body_plain="Body",
            mode=EmailMode.DRAFT_ONLY,
        )
        result = engine.validate_email(draft)
        assert not result.passed

    # ── Meeting request validation ─────────────────────────────────────────────

    def test_valid_meeting_request_passes(self):
        engine = GovernanceEngine()
        request = MeetingRequest(
            action_id="a-001",
            meeting_id="m-001",
            subject="APM Impact Review",
            objective="Confirm APM impact with team",
            required_attendees=["alice@example.com", "bob@example.com"],
            agenda=["Review APM data", "Agree on action plan"],
            mode=SchedulingMode.DRAFT_ONLY,
        )
        result = engine.validate_meeting_request(request)
        assert result.passed

    def test_no_attendees_fails(self):
        engine = GovernanceEngine()
        request = MeetingRequest(
            action_id="a-001",
            meeting_id="m-001",
            subject="Empty meeting",
            objective="Something",
            required_attendees=[],
            mode=SchedulingMode.DRAFT_ONLY,
        )
        result = engine.validate_meeting_request(request)
        assert not result.passed
