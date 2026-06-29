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


def _get_agent(config: Optional[str] = None, use_outlook: bool = False):
    """Lazy import to keep CLI startup fast."""
    from meeting_agent.agent import MeetingFollowUpAgent
    settings = load_settings(config)
    graph_client = None
    if use_outlook:
        from meeting_agent.integrations.outlook_com import OutlookCOMClient
        graph_client = OutlookCOMClient()
        console.print("[cyan]Using local Outlook (COM) — no Azure AD permissions required.[/cyan]")
    return MeetingFollowUpAgent(settings=settings, graph_client=graph_client)


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def process(
    meeting_id: Optional[str] = typer.Option(None, "--meeting-id", "-m", help="Process a specific meeting by ID"),
    all_pending: bool = typer.Option(False, "--all", "-a", help="Process all pending meetings"),
    lookback: int = typer.Option(24, "--lookback", help="Lookback window in hours (used with --all)"),
    use_outlook: bool = typer.Option(False, "--use-outlook", help="Use local Outlook COM instead of Graph API (no admin consent needed)"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml"),
) -> None:
    """Process meeting(s) and extract action items."""
    if not meeting_id and not all_pending:
        console.print("[red]Specify --meeting-id <id> or --all[/red]")
        raise typer.Exit(1)

    agent = _get_agent(config, use_outlook=use_outlook)

    if meeting_id:
        result = agent.process_meeting(meeting_id)
        _print_result(result)
    else:
        results = agent.process_all_pending(lookback_hours=lookback)
        console.print(f"\nProcessed [bold]{len(results)}[/bold] meeting(s).")
        for r in results:
            _print_result(r)


@app.command(name="from-file")
def from_file(
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Path to facilitator notes (.txt / .md)"),
    transcript: Optional[str] = typer.Option(None, "--transcript", "-t", help="Path to transcript file"),
    chat: Optional[str] = typer.Option(None, "--chat", "-c", help="Path to chat export file"),
    title: str = typer.Option("Meeting", "--title", help="Meeting title"),
    date: str = typer.Option(None, "--date", "-d", help="Meeting date ISO format e.g. 2026-06-26T10:00 (defaults to now)"),
    meeting_id: str = typer.Option(None, "--meeting-id", "-m", help="Optional stable ID for this meeting"),
    use_outlook: bool = typer.Option(False, "--use-outlook", help="Save email drafts to local Outlook"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Process a meeting from local files — no Microsoft 365 connection required."""
    from datetime import datetime as dt
    from meeting_agent.engines.ingestion import MeetingIngestionEngine
    from meeting_agent.engines.extraction import ActionExtractionEngine
    from meeting_agent.engines.ownership import OwnershipEngine
    from meeting_agent.engines.followup import FollowUpEngine
    from meeting_agent.engines.email_generation import EmailGenerationEngine
    from meeting_agent.engines.task_management import TaskManagementEngine
    from meeting_agent.engines.governance import GovernanceEngine
    from meeting_agent.engines.documentation import DocumentationEngine
    import uuid

    if not notes and not transcript and not chat:
        console.print("[red]Provide at least one of --notes, --transcript, or --chat[/red]")
        raise typer.Exit(1)

    settings = load_settings(config)
    graph_client = None
    if use_outlook:
        from meeting_agent.integrations.outlook_com import OutlookCOMClient
        graph_client = OutlookCOMClient()

    mid = meeting_id or str(uuid.uuid4())[:8]
    date_str = date or dt.now().isoformat()

    console.print(f"\nProcessing meeting [bold]{title}[/bold] from local files...")

    ingestion   = MeetingIngestionEngine(settings)
    extraction  = ActionExtractionEngine(settings)
    ownership   = OwnershipEngine(settings)
    followup    = FollowUpEngine(settings)
    email_gen   = EmailGenerationEngine(settings, graph_client=graph_client)
    task_engine = TaskManagementEngine(settings)
    governance  = GovernanceEngine()
    doc_engine  = DocumentationEngine(settings, task_engine)

    context = ingestion.ingest_from_files(
        meeting_id=mid,
        title=title,
        date_str=date_str,
        notes_path=notes,
        transcript_path=transcript,
        chat_path=chat,
    )

    actions = extraction.extract(context)
    ownership.resolve(actions, context)
    plans   = followup.build_plans(actions, context)
    emails  = email_gen.generate(actions, plans, context)
    tasks   = [task_engine.upsert_from_action(a, mid) for a in actions]
    summary = doc_engine.generate_meeting_summary(context, tasks)

    _print_result({
        "meeting_id": mid,
        "tasks": tasks,
        "emails": emails,
        "meeting_requests": [],
        "summary": summary,
    })


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

@app.command(name="fetch-notes")
def fetch_notes(
    title: str = typer.Option(..., "--title", "-t", help="Meeting title"),
    facilitator: Optional[str] = typer.Option(None, "--facilitator", "-f", help="Facilitator email address to filter by"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Subject keyword to filter by (e.g. 'meeting notes')"),
    lookback: int = typer.Option(24, "--lookback", help="Hours to look back in inbox (default 24)"),
    config: Optional[str] = typer.Option(None, "--config"),
) -> None:
    """Fetch facilitator notes from Outlook inbox and process automatically."""
    from meeting_agent.integrations.outlook_com import OutlookCOMClient

    settings = load_settings(config)
    outlook = OutlookCOMClient()

    console.print(f"\n[cyan]Searching Outlook inbox (last {lookback}h)...[/cyan]")
    email = outlook.fetch_facilitator_notes(
        sender_email=facilitator,
        subject_keyword=keyword,
        lookback_hours=lookback,
    )

    if not email:
        console.print("[red]No matching email found. Try --facilitator or --keyword to narrow the search.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Found:[/green] '{email['subject']}' from {email['sender']} at {email['received_time']}")

    # Write body to a temp file and process
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(email["body"])
        tmp_path = tmp.name

    try:
        from meeting_agent.engines.ingestion import MeetingIngestionEngine
        from meeting_agent.engines.extraction import ActionExtractionEngine
        from meeting_agent.engines.ownership import OwnershipEngine
        from meeting_agent.engines.followup import FollowUpEngine
        from meeting_agent.engines.email_generation import EmailGenerationEngine
        from meeting_agent.engines.task_management import TaskManagementEngine
        from meeting_agent.engines.governance import GovernanceEngine
        from meeting_agent.engines.documentation import DocumentationEngine
        from datetime import datetime as dt
        import uuid

        mid = str(uuid.uuid4())[:8]
        date_str = email["received_time"].isoformat()

        ingestion   = MeetingIngestionEngine(settings, graph_client=outlook)
        extraction  = ActionExtractionEngine(settings)
        ownership   = OwnershipEngine(settings)
        followup    = FollowUpEngine(settings)
        email_gen   = EmailGenerationEngine(settings, graph_client=outlook)
        task_engine = TaskManagementEngine(settings)
        governance  = GovernanceEngine()
        doc_engine  = DocumentationEngine(settings, task_engine)

        context = ingestion.ingest_from_files(
            meeting_id=mid, title=title, date_str=date_str, notes_path=tmp_path,
        )
        actions = extraction.extract(context)
        ownership.resolve(actions, context)
        plans   = followup.build_plans(actions, context)
        emails  = email_gen.generate(actions, plans, context)
        tasks   = [task_engine.upsert_from_action(a, mid) for a in actions]
        summary = doc_engine.generate_meeting_summary(context, tasks)
        _print_result({"meeting_id": mid, "tasks": tasks, "emails": emails,
                       "meeting_requests": [], "summary": summary})
    finally:
        os.unlink(tmp_path)


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
