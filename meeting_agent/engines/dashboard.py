from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from meeting_agent.engines.task_management import TaskManagementEngine
from meeting_agent.models.action import ActionStatus, ActionPriority
from meeting_agent.models.task import Task

console = Console()


class DashboardEngine:
    """
    MODULE 11 — Provide executive visibility via Rich terminal tables.

    Views:
      1. My Open Actions
      2. Actions By Meeting
      3. Overdue Actions
      4. Waiting For Response
      5. Upcoming Follow-Ups
      6. Actions Assigned To Others
    """

    def __init__(self, task_engine: TaskManagementEngine, primary_user: str) -> None:
        self._tasks = task_engine
        self._primary_user = primary_user

    # ── Public views ──────────────────────────────────────────────────────────

    def my_open_actions(self) -> None:
        tasks = [
            t for t in self._tasks.get_open()
            if t.owner and self._primary_user.lower() in t.owner.lower()
        ]
        self._render_table("My Open Actions", tasks)

    def overdue_actions(self) -> None:
        tasks = self._tasks.get_overdue()
        self._render_table("Overdue Actions", tasks, highlight_overdue=True)

    def waiting_for_response(self) -> None:
        tasks = [
            t for t in self._tasks.get_open()
            if t.status == ActionStatus.WAITING_RESPONSE
        ]
        self._render_table("Waiting For Response", tasks)

    def actions_by_meeting(self, meeting_id: str) -> None:
        tasks = self._tasks.get_by_meeting(meeting_id)
        self._render_table(f"Actions for Meeting {meeting_id[:12]}…", tasks)

    def actions_assigned_to_others(self) -> None:
        tasks = [
            t for t in self._tasks.get_open()
            if t.owner and self._primary_user.lower() not in t.owner.lower()
        ]
        self._render_table("Actions Assigned To Others", tasks)

    def metrics_summary(self) -> None:
        all_tasks = self._tasks.get_all()
        open_count = sum(1 for t in all_tasks if t.status not in [ActionStatus.COMPLETED, ActionStatus.CANCELLED])
        completed = sum(1 for t in all_tasks if t.status == ActionStatus.COMPLETED)
        overdue = sum(1 for t in all_tasks if t.is_overdue())

        console.print(f"\n[bold]Action Metrics — {datetime.utcnow().date()}[/bold]")
        console.print(f"  Total     : {len(all_tasks)}")
        console.print(f"  Open      : [yellow]{open_count}[/yellow]")
        console.print(f"  Completed : [green]{completed}[/green]")
        console.print(f"  Overdue   : [red]{overdue}[/red]")

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _render_table(title: str, tasks: list[Task], highlight_overdue: bool = False) -> None:
        table = Table(title=title, show_lines=True)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Description")
        table.add_column("Owner")
        table.add_column("Due")
        table.add_column("Priority")
        table.add_column("Status")

        for t in tasks:
            due_str = t.due_date.date().isoformat() if t.due_date else "—"
            style = "red" if highlight_overdue and t.is_overdue() else ""
            priority_colour = {"high": "red", "medium": "yellow", "low": "green"}.get(
                t.priority.value, ""
            )
            table.add_row(
                t.task_id[:8],
                t.description[:70],
                t.owner or "—",
                due_str,
                f"[{priority_colour}]{t.priority.value}[/{priority_colour}]",
                t.status.value,
                style=style,
            )

        console.print(table)
        if not tasks:
            console.print(f"  [dim]No items in '{title}'[/dim]")
