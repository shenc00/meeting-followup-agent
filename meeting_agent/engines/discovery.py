from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from meeting_agent.config import Settings
from meeting_agent.models.meeting import MeetingContext, MeetingSource

logger = logging.getLogger(__name__)


class PendingMeeting:
    """Lightweight descriptor returned by the discovery engine."""

    def __init__(
        self,
        meeting_id: str,
        title: str,
        date: datetime,
        source: MeetingSource,
        has_notes: bool = False,
        has_transcript: bool = False,
        has_chat: bool = False,
    ) -> None:
        self.meeting_id = meeting_id
        self.title = title
        self.date = date
        self.source = source
        self.has_notes = has_notes
        self.has_transcript = has_transcript
        self.has_chat = has_chat

    def __repr__(self) -> str:
        return f"PendingMeeting(id={self.meeting_id!r}, title={self.title!r})"


class MeetingDiscoveryEngine:
    """
    MODULE 1 — Identify meetings that have ended and require processing.

    Discovery order:
      1. Teams calendar events completed in the lookback window
      2. Outlook calendar events
      3. Manually queued meeting IDs

    Uses the Graph API integration to query calendar events.
    """

    def __init__(self, settings: Settings, graph_client=None) -> None:
        self.settings = settings
        self._graph = graph_client  # injected; None in offline/test mode

    def discover_pending(
        self,
        lookback_hours: int = 24,
        already_processed: Optional[set[str]] = None,
    ) -> list[PendingMeeting]:
        """
        Return meetings that ended within `lookback_hours` and have not yet
        been processed.
        """
        already_processed = already_processed or set()

        if self._graph is None:
            logger.warning(
                "No Graph client configured — discovery returning empty queue"
            )
            return []

        try:
            events = self._graph.get_recent_calendar_events(lookback_hours=lookback_hours)
        except Exception as exc:
            logger.error("Graph calendar query failed: %s", exc)
            return []

        pending: list[PendingMeeting] = []
        for event in events:
            mid = event.get("id", "")
            if mid in already_processed:
                continue
            pending.append(
                PendingMeeting(
                    meeting_id=mid,
                    title=event.get("subject", "Untitled"),
                    date=self._parse_event_date(event),
                    source=MeetingSource.TEAMS if event.get("isOnlineMeeting") else MeetingSource.OUTLOOK,
                    has_notes=bool(event.get("body")),
                    has_transcript=event.get("hasTranscript", False),
                    has_chat=event.get("hasChat", False),
                )
            )

        logger.info("Discovered %d pending meeting(s)", len(pending))
        return pending

    def queue_manual(self, meeting_id: str) -> PendingMeeting:
        """Allow a meeting to be force-queued by ID for ad-hoc processing."""
        return PendingMeeting(
            meeting_id=meeting_id,
            title="(manual queue)",
            date=datetime.utcnow(),
            source=MeetingSource.MANUAL,
        )

    @staticmethod
    def _parse_event_date(event: dict) -> datetime:
        try:
            return datetime.fromisoformat(
                event.get("start", {}).get("dateTime", "").rstrip("Z")
            )
        except Exception:
            return datetime.utcnow()
