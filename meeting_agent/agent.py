from __future__ import annotations

import logging
from typing import Optional

from meeting_agent.config import Settings, load_settings
from meeting_agent.engines.discovery import MeetingDiscoveryEngine
from meeting_agent.engines.documentation import DocumentationEngine
from meeting_agent.engines.email_generation import EmailGenerationEngine
from meeting_agent.engines.extraction import ActionExtractionEngine
from meeting_agent.engines.followup import FollowUpEngine
from meeting_agent.engines.governance import GovernanceEngine
from meeting_agent.engines.ingestion import MeetingIngestionEngine
from meeting_agent.engines.memory import MeetingMemoryEngine
from meeting_agent.engines.ownership import OwnershipEngine
from meeting_agent.engines.reminder import ReminderEngine
from meeting_agent.engines.scheduling import SchedulingEngine
from meeting_agent.engines.task_management import TaskManagementEngine

logger = logging.getLogger(__name__)


class MeetingFollowUpAgent:
    """
    Top-level orchestrator.

    Wires all 13 engines together and exposes the end-to-end
    `process_meeting` pipeline.
    """

    def __init__(self, settings: Optional[Settings] = None, graph_client=None) -> None:
        self.settings = settings or load_settings()
        g = graph_client

        # Engines
        self.discovery = MeetingDiscoveryEngine(self.settings, graph_client=g)
        self.ingestion = MeetingIngestionEngine(self.settings, graph_client=g)
        self.extraction = ActionExtractionEngine(self.settings)
        self.ownership = OwnershipEngine(self.settings)
        self.followup = FollowUpEngine(self.settings)
        self.email_gen = EmailGenerationEngine(self.settings, graph_client=g)
        self.scheduling = SchedulingEngine(self.settings, graph_client=g)
        self.task_mgmt = TaskManagementEngine(self.settings)
        self.reminder = ReminderEngine(self.settings, self.task_mgmt)
        self.memory = MeetingMemoryEngine(self.settings, self.task_mgmt)
        self.documentation = DocumentationEngine(self.settings, self.task_mgmt)
        self.governance = GovernanceEngine()

    # ── Primary pipeline ──────────────────────────────────────────────────────

    def process_meeting(self, meeting_id: str) -> dict:
        """
        Full end-to-end pipeline for a single meeting.

        Returns a results dict containing tasks, emails, meeting requests,
        summary, and historical links.
        """
        logger.info("=== Processing meeting %s ===", meeting_id)

        # Step 1: Ingest
        pending = self.discovery.queue_manual(meeting_id)
        context = self.ingestion.ingest(pending)

        # Step 2: Cross-meeting memory lookup
        historical_links = self.memory.find_historical_links(context)

        # Step 3: Extract actions
        actions = self.extraction.extract(context)
        if not actions:
            logger.info("No actions extracted from meeting %s", meeting_id)

        # Step 4: Resolve ownership
        self.ownership.resolve(actions, context)

        # Step 5: Governance — validate actions
        for action in actions:
            result = self.governance.validate_action(action, context)
            self.governance.log_result(result, context=action.action_id[:8])

        # Step 6: Build follow-up plans (resolves due dates)
        plans = self.followup.build_plans(actions, context)

        # Step 7: Generate emails
        emails = self.email_gen.generate(actions, plans, context)

        # Step 8: Governance — validate emails
        for email in emails:
            result = self.governance.validate_email(email)
            self.governance.log_result(result, context=email.email_id[:8])

        # Step 9: Schedule meetings
        meeting_requests = self.scheduling.schedule(actions, plans, context)

        # Step 10: Persist tasks
        tasks = [self.task_mgmt.upsert_from_action(a, meeting_id) for a in actions]

        # Step 11: Store meeting in memory
        self.memory.store_meeting(context)

        # Step 12: Generate executive summary
        summary = self.documentation.generate_meeting_summary(context, tasks)

        logger.info(
            "=== Meeting %s processed: %d action(s), %d email(s), %d meeting request(s) ===",
            meeting_id, len(tasks), len(emails), len(meeting_requests),
        )

        return {
            "meeting_id": meeting_id,
            "tasks": tasks,
            "emails": emails,
            "meeting_requests": meeting_requests,
            "historical_links": historical_links,
            "summary": summary,
        }

    def process_all_pending(self, lookback_hours: int = 24) -> list[dict]:
        """Discover and process all unprocessed meetings in the lookback window."""
        already_processed = {m.get("meeting_id", "") for m in self.memory.get_previous_meetings(200)}
        pending_list = self.discovery.discover_pending(
            lookback_hours=lookback_hours,
            already_processed=already_processed,
        )
        results = []
        for pending in pending_list:
            try:
                result = self.process_meeting(pending.meeting_id)
                results.append(result)
            except Exception as exc:
                logger.error("Failed to process meeting %s: %s", pending.meeting_id, exc)
        return results
