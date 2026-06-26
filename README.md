# Meeting Follow-Up Automation Agent

An AI-powered executive assistant that automatically processes meeting outcomes
and converts them into actionable tasks, Outlook emails, calendar invitations,
follow-ups, and a personal action repository.

## Overview

After every meeting the agent automatically:

- Reads facilitator notes, transcripts, and chat logs
- Extracts all action items with owners and due dates
- Drafts required Outlook emails (draft / approval / auto-send)
- Creates calendar invitations when a follow-up meeting is required
- Maintains a persistent action repository until each item is closed
- Provides cross-meeting memory so repeated topics are linked
- Generates executive summaries and open-action dashboards

## Architecture

```
MeetingFollowUpAgent
│
├── MeetingDiscoveryEngine     — Detect completed meetings requiring processing
├── MeetingIngestionEngine     — Aggregate notes / transcript / chat into context
├── ActionExtractionEngine     — Extract structured action items with evidence
├── OwnershipEngine            — Resolve and score action ownership
├── FollowUpEngine             — Determine next steps per action
├── EmailGenerationEngine      — Draft complete Outlook emails
├── SchedulingEngine           — Create calendar / Teams invitations
├── TaskManagementEngine       — Persistent, queryable action repository
├── ReminderEngine             — Overdue / no-response detection and escalation
├── MeetingMemoryEngine        — Cross-meeting historical context
├── DashboardEngine            — Executive metrics and open-action views
├── DocumentationEngine        — Meeting summaries and weekly/monthly reports
└── GovernanceEngine           — Validation and approval guardrails
```

## Quickstart

```bash
# 1. Clone
git clone https://github.com/<org>/meeting-followup-agent
cd meeting-followup-agent

# 2. Configure
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml — add Graph API credentials and OpenAI key

# 3. Install
pip install -e .

# 4. Authenticate with Microsoft 365
meeting-agent auth login

# 5. Process all pending meetings
meeting-agent process --all

# 6. View open-actions dashboard
meeting-agent dashboard

# 7. Check reminders
meeting-agent reminders

# 8. Generate weekly summary
meeting-agent report --weekly
```

## Configuration Reference

See [config/config.yaml.example](config/config.yaml.example).

| Setting | Values | Description |
|---|---|---|
| `email_mode` | `draft` \| `approval` \| `auto_send` | How emails are handled |
| `scheduling_mode` | `draft` \| `approval` \| `auto_schedule` | How meetings are created |
| `primary_user.name` | string | Your display name as it appears in meetings |
| `primary_user.email` | string | Your email address |
| `reminder.no_response_days` | int | Days before sending a reminder (default 5) |
| `reminder.escalation_days` | int | Days before escalating (default 14) |

## Design Principles

| # | Principle | Behaviour |
|---|---|---|
| 1 | Accuracy First | Never invent actions, owners, deadlines, or requirements |
| 2 | Deterministic First | Use rule-based extraction before AI wherever possible |
| 3 | Explainability | Every extracted action carries verbatim source evidence |
| 4 | Human Confirmation | High-impact actions require configurable approval levels |
| 5 | Traceability | Every email / meeting / task links back to the originating meeting |
| 6 | Continuous Follow-Up | Open actions persist and surface until marked complete |

## Requirements

- Python 3.11+
- Microsoft 365 account with Graph API permissions:
  - `Mail.ReadWrite`, `Mail.Send`
  - `Calendars.ReadWrite`
  - `OnlineMeetings.ReadWrite`
  - `Chat.Read`
- Azure OpenAI **or** OpenAI API key

## Project Structure

```
meeting_agent/
├── models/          Pydantic data models
├── skills/          AI prompt-based extraction skills
├── engines/         Orchestration engines (one per module)
├── integrations/    Microsoft Graph API connectors
├── cli.py           Typer CLI entry point
└── config.py        Config loading
config/              YAML configuration
tests/               Pytest test suite
```
