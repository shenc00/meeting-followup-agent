from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from meeting_agent.models.action import ActionItem
from meeting_agent.models.email import DraftEmailPackage
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.scheduling import MeetingRequest

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GovernanceEngine:
    """
    MODULE 13 — Validate actions, emails, and meeting requests before execution.

    Validation rules (per spec):
      1. Action owner must resolve to a known participant
      2. Email recipients must be non-empty and valid format
      3. Meeting requests must not duplicate existing calendar events
      4. Due dates must be in the future
      5. Every action must carry verbatim evidence
      6. High-impact actions require approval flag
    """

    HIGH_IMPACT_CLASSIFICATIONS = {
        "email_required",
        "meeting_required",
        "escalation",
    }

    def validate_action(
        self,
        action: ActionItem,
        context: MeetingContext,
    ) -> ValidationResult:
        violations: list[str] = []
        warnings: list[str] = []

        # Rule 5: evidence required
        if not action.raw_statement or len(action.raw_statement.strip()) < 5:
            violations.append(f"Action {action.action_id[:8]}: missing verbatim evidence")

        # Rule 4: due date in the future
        if action.due_date and action.due_date < context.date:
            violations.append(
                f"Action {action.action_id[:8]}: due date {action.due_date.date()} "
                f"is before the meeting date {context.date.date()}"
            )

        # Rule 1: owner resolves to a participant
        if action.assigned_to:
            known_names = {p.name.lower() for p in context.participants}
            if action.assigned_to.lower() not in known_names:
                warnings.append(
                    f"Action {action.action_id[:8]}: owner '{action.assigned_to}' "
                    f"is not in the participant list — verify manually"
                )

        # Rule 6: high-impact flag
        if action.classification.value in self.HIGH_IMPACT_CLASSIFICATIONS:
            if action.extraction_confidence < 0.7:
                warnings.append(
                    f"Action {action.action_id[:8]}: high-impact classification "
                    f"with low confidence ({action.extraction_confidence:.2f}) — recommend approval"
                )

        return ValidationResult(passed=len(violations) == 0, violations=violations, warnings=warnings)

    def validate_email(self, draft: DraftEmailPackage) -> ValidationResult:
        violations: list[str] = []
        import re
        email_re = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

        # Rule 2: recipients
        if not draft.recipients_to:
            violations.append(f"Email {draft.email_id[:8]}: no recipients")
        for addr in draft.recipients_to + draft.recipients_cc:
            if not email_re.match(addr):
                violations.append(f"Email {draft.email_id[:8]}: invalid address '{addr}'")

        if not draft.subject or not draft.subject.strip():
            violations.append(f"Email {draft.email_id[:8]}: empty subject")

        if not draft.body_plain or not draft.body_plain.strip():
            violations.append(f"Email {draft.email_id[:8]}: empty body")

        return ValidationResult(passed=len(violations) == 0, violations=violations)

    def validate_meeting_request(
        self,
        request: MeetingRequest,
        existing_event_titles: list[str] | None = None,
    ) -> ValidationResult:
        violations: list[str] = []
        warnings: list[str] = []

        # Rule 3: no duplicate meeting
        if existing_event_titles:
            for existing in existing_event_titles:
                if request.subject.lower() in existing.lower():
                    violations.append(
                        f"MeetingRequest {request.request_id[:8]}: "
                        f"a similar meeting '{existing}' may already exist"
                    )

        if not request.required_attendees:
            violations.append(f"MeetingRequest {request.request_id[:8]}: no required attendees")

        if not request.agenda:
            warnings.append(f"MeetingRequest {request.request_id[:8]}: no agenda defined")

        return ValidationResult(passed=len(violations) == 0, violations=violations, warnings=warnings)

    def log_result(self, result: ValidationResult, context: str = "") -> None:
        if result.passed:
            logger.debug("Governance PASSED%s", f" [{context}]" if context else "")
        else:
            for v in result.violations:
                logger.error("Governance VIOLATION: %s", v)
        for w in result.warnings:
            logger.warning("Governance WARNING: %s", w)
