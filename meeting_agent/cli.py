from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console

from meeting_agent.config import load_settings

app = typer.Typer(
    name="meeting-agent",
    help="AI-powered executive assistant for meeting follow-up automation.",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger(__name__)


def _get_agent(config: Optional[str] = None):
    """Lazy import to keep CLI startup fast."""
    from meeting_agent.agent import MeetingFollowUpAgent
    settings = load_settings(config)
    return MeetingFollowUpAgent(settings=settings)


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def process(
    meeting_id: Optional[str] = typer.Option(None, "--meeting-id", "-m", help="Process a specific meeting by ID"),
    all_pending: bool = typer.Option(False, "--all", "-a", help="Process all pending meetings"),
    lookback: int = typer.Option(24, "--lookback", help="Lookback window in hours (used with --all)"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml"),
) -> None:
    """Process meeting(s) and extract action items."""
    if not meeting_id and not all_pending:
        console.print("[red]Specify --meeting-id <id> or --all[/red]")
        raise typer.Exit(1)

    agent = _get_agent(config)

    if meeting_id:
        result = agent.process_meeting(meeting_id)
        _print_result(result)
    else:
        results = agent.process_all_pending(lookback_hours=lookback)
        console.print(f"\nProcessed [bold]{len(results)}[/bold] meeting(s).")
        for r in results:
            _print_result(r)


@app.command()
def dashboard(
    view: str = typer.Option("open", "--view", "-v", help="open | overdue | waiting | others | meeting"),
    meeting_id: Optional[str] = typer.Option(None, "--meeting-id", help="Required for --view meeting"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Display the action dashboard."""
    settings = load_settings(config)
    from meeting_agent.engines.task_management import TaskManagementEngine
    from meeting_agent.engines.dashboard import DashboardEngine

    task_engine = TaskManagementEngine(settings)
    dash = DashboardEngine(task_engine, settings.primary_user.name)

    dash.metrics_summary()

    if view == "open":
        dash.my_open_actions()
    elif view == "overdue":
        dash.overdue_actions()
    elif view == "waiting":
        dash.waiting_for_response()
    elif view == "others":
        dash.actions_assigned_to_others()
    elif view == "meeting":
        if not meeting_id:
            console.print("[red]--meeting-id required for --view meeting[/red]")
            raise typer.Exit(1)
        dash.actions_by_meeting(meeting_id)
    else:
        console.print(f"[red]Unknown view '{view}'[/red]")
        raise typer.Exit(1)


@app.command()
def reminders(
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Display reminders for overdue and no-response actions."""
    settings = load_settings(config)
    from meeting_agent.engines.task_management import TaskManagementEngine
    from meeting_agent.engines.reminder import ReminderEngine

    task_engine = TaskManagementEngine(settings)
    reminder_engine = ReminderEngine(settings, task_engine)
    summary_text = reminder_engine.generate_daily_summary()
    console.print(summary_text)


@app.command()
def report(
    weekly: bool = typer.Option(False, "--weekly", help="Generate weekly summary"),
    monthly: bool = typer.Option(False, "--monthly", help="Generate monthly report"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Generate action reports."""
    settings = load_settings(config)
    from meeting_agent.engines.task_management import TaskManagementEngine
    from meeting_agent.engines.documentation import DocumentationEngine

    task_engine = TaskManagementEngine(settings)
    doc_engine = DocumentationEngine(settings, task_engine)

    if weekly:
        console.print(doc_engine.generate_weekly_summary())
    if monthly:
        console.print(doc_engine.generate_monthly_report())
    if not weekly and not monthly:
        console.print("[red]Specify --weekly or --monthly[/red]")
        raise typer.Exit(1)


@app.command()
def task(
    task_id: str = typer.Argument(..., help="Task ID to update"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status"),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Add a note"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Update a task status or add a note."""
    settings = load_settings(config)
    from meeting_agent.engines.task_management import TaskManagementEngine
    from meeting_agent.models.action import ActionStatus

    task_engine = TaskManagementEngine(settings)

    if status:
        try:
            new_status = ActionStatus(status)
        except ValueError:
            console.print(f"[red]Invalid status '{status}'. Valid: {[s.value for s in ActionStatus]}[/red]")
            raise typer.Exit(1)
        success = task_engine.update_status(task_id, new_status)
        console.print("[green]Status updated.[/green]" if success else "[red]Task not found.[/red]")

    if note:
        success = task_engine.add_note(task_id, note)
        console.print("[green]Note added.[/green]" if success else "[red]Task not found.[/red]")


@app.command(name="auth")
def auth_login(
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Authenticate with Microsoft Graph (interactive device code flow)."""
    settings = load_settings(config)
    from meeting_agent.integrations.auth import GraphAuthClient

    auth = GraphAuthClient(
        tenant_id=settings.graph.tenant_id,
        client_id=settings.graph.client_id,
        client_secret=settings.graph.client_secret,
        scopes=settings.graph.scopes,
        cache_path=settings.graph.token_cache_path,
    )
    token = auth.get_token()
    if token:
        console.print("[green]Authentication successful.[/green]")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_result(result: dict) -> None:
    mid = result.get("meeting_id", "")[:12]
    tasks = result.get("tasks", [])
    emails = result.get("emails", [])
    requests = result.get("meeting_requests", [])
    summary = result.get("summary", {})

    console.rule(f"Meeting {mid}…")
    console.print(f"  Tasks extracted   : [bold]{len(tasks)}[/bold]")
    console.print(f"  Emails drafted    : [bold]{len(emails)}[/bold]")
    console.print(f"  Meeting requests  : [bold]{len(requests)}[/bold]")
    if summary.get("full_text"):
        console.print("\n[italic]Summary:[/italic]")
        console.print(summary["full_text"][:500])
