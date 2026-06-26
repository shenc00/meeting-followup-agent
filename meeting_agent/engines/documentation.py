from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from jinja2 import Environment, PackageLoader, select_autoescape

from meeting_agent.config import Settings
from meeting_agent.engines.task_management import TaskManagementEngine
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.task import Task
from meeting_agent.skills.executive_summary import ExecutiveSummarySkill

logger = logging.getLogger(__name__)


class DocumentationEngine:
    """
    MODULE 12 — Generate structured meeting and action documentation.

    Documents produced:
      - Meeting summary (per meeting)
      - Action summary (per meeting)
      - Weekly executive summary
      - Monthly action report
    """

    def __init__(self, settings: Settings, task_engine: TaskManagementEngine) -> None:
        self.settings = settings
        self._tasks = task_engine
        self._skill = ExecutiveSummarySkill(settings)
        self._jinja = Environment(
            loader=PackageLoader("meeting_agent", "templates"),
            autoescape=select_autoescape(["html"]),
        )

    def generate_meeting_summary(
        self, context: MeetingContext, tasks: list[Task]
    ) -> dict:
        """Generate and return the executive summary dict for a single meeting."""
        try:
            summary = self._skill.run(context=context, tasks=tasks)
            logger.info("Meeting summary generated for %s", context.meeting_id)
            return summary
        except Exception as exc:
            logger.error("Summary generation failed: %s", exc)
            return {
                "overview": f"Meeting: {context.title} on {context.date.date()}",
                "key_decisions": [],
                "action_items_summary": [t.description for t in tasks],
                "risks": [],
                "next_steps": [],
                "full_text": "(summary generation failed)",
            }

    def generate_weekly_summary(self) -> str:
        """Produce a weekly open-action report covering the last 7 days."""
        cutoff = datetime.utcnow() - timedelta(days=7)
        tasks = [
            t for t in self._tasks.get_all()
            if t.created_at >= cutoff
        ]
        open_count = sum(1 for t in tasks if t.status.value not in ("completed", "cancelled"))
        completed_count = sum(1 for t in tasks if t.status.value == "completed")

        lines = [
            f"=== Weekly Summary — {datetime.utcnow().date()} ===",
            f"Actions created this week : {len(tasks)}",
            f"Open                      : {open_count}",
            f"Completed                 : {completed_count}",
            "",
            "OPEN ACTIONS:",
        ]
        for t in tasks:
            if t.status.value not in ("completed", "cancelled"):
                lines.append(
                    f"  [{t.task_id[:8]}] {t.description} | owner: {t.owner or 'TBD'}"
                )
        return "\n".join(lines)

    def generate_monthly_report(self) -> str:
        """Produce a monthly action closure report."""
        cutoff = datetime.utcnow() - timedelta(days=30)
        tasks = [t for t in self._tasks.get_all() if t.created_at >= cutoff]
        completed = [t for t in tasks if t.status.value == "completed"]
        overdue = [t for t in tasks if t.is_overdue()]

        lines = [
            f"=== Monthly Report — {datetime.utcnow().date()} ===",
            f"Total actions : {len(tasks)}",
            f"Completed     : {len(completed)}",
            f"Overdue       : {len(overdue)}",
        ]
        return "\n".join(lines)
