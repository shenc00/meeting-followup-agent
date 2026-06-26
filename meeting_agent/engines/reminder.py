from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from meeting_agent.config import Settings
from meeting_agent.engines.task_management import TaskManagementEngine
from meeting_agent.models.task import Task

logger = logging.getLogger(__name__)


class ReminderSummary:
    def __init__(self) -> None:
        self.overdue: list[Task] = []
        self.no_response: list[Task] = []
        self.escalation_candidates: list[Task] = []

    def is_empty(self) -> bool:
        return not (self.overdue or self.no_response or self.escalation_candidates)


class ReminderEngine:
    """
    MODULE 9 — Detect and surface actions that require reminders or escalation.

    Rules (configured in settings):
      - no_response_days: days after last reminder before drafting a new reminder
      - escalation_days: days of no progress before recommending escalation
    """

    def __init__(self, settings: Settings, task_engine: TaskManagementEngine) -> None:
        self.settings = settings
        self._tasks = task_engine
        self._no_response_threshold = timedelta(days=settings.reminder.no_response_days)
        self._escalation_threshold = timedelta(days=settings.reminder.escalation_days)

    def scan(self) -> ReminderSummary:
        """Scan all open tasks and classify those needing attention."""
        now = datetime.utcnow()
        summary = ReminderSummary()

        for task in self._tasks.get_open():
            if task.is_overdue():
                summary.overdue.append(task)

            if self._needs_reminder(task, now):
                summary.no_response.append(task)

            if self._needs_escalation(task, now):
                summary.escalation_candidates.append(task)

        logger.info(
            "Reminder scan: overdue=%d no_response=%d escalation=%d",
            len(summary.overdue),
            len(summary.no_response),
            len(summary.escalation_candidates),
        )
        return summary

    def generate_daily_summary(self) -> str:
        summary = self.scan()
        lines: list[str] = [f"=== Daily Action Summary — {datetime.utcnow().date()} ===\n"]

        if summary.overdue:
            lines.append(f"OVERDUE ({len(summary.overdue)}):")
            for t in summary.overdue:
                lines.append(f"  - [{t.task_id[:8]}] {t.description} | due {t.due_date}")

        if summary.no_response:
            lines.append(f"\nAWAITING RESPONSE ({len(summary.no_response)}):")
            for t in summary.no_response:
                lines.append(f"  - [{t.task_id[:8]}] {t.description}")

        if summary.escalation_candidates:
            lines.append(f"\nRECOMMEND ESCALATION ({len(summary.escalation_candidates)}):")
            for t in summary.escalation_candidates:
                lines.append(f"  - [{t.task_id[:8]}] {t.description}")

        if summary.is_empty():
            lines.append("No open actions requiring attention.")

        return "\n".join(lines)

    # ── Private ───────────────────────────────────────────────────────────────

    def _needs_reminder(self, task: Task, now: datetime) -> bool:
        last = task.last_reminder_sent_at or task.created_at
        return (now - last) >= self._no_response_threshold

    def _needs_escalation(self, task: Task, now: datetime) -> bool:
        if task.escalated_at:
            return False
        return (now - task.created_at) >= self._escalation_threshold
