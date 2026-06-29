from __future__ import annotations

import logging
import re

from meeting_agent.config import Settings
from meeting_agent.engines.discovery import PendingMeeting
from meeting_agent.models.meeting import MeetingContext, MeetingParticipant

logger = logging.getLogger(__name__)


class MeetingIngestionEngine:
    """
    MODULE 2 — Retrieve and normalise all content associated with a meeting.

    Priority order (matches spec):
      1. Facilitator Notes
      2. Transcript
      3. Chat
      4. Meeting Description / Body
      5. Attachments / Shared Files
    """

    def __init__(self, settings: Settings, graph_client=None) -> None:
        self.settings = settings
        self._graph = graph_client

    def ingest(self, pending: PendingMeeting) -> MeetingContext:
        """
        Fetch all content for a pending meeting and return a normalised
        MeetingContext ready for action extraction.
        """
        logger.info("Ingesting meeting %s — %s", pending.meeting_id, pending.title)

        raw_event: dict = {}
        if self._graph:
            try:
                raw_event = self._graph.get_event(pending.meeting_id) or {}
            except Exception as exc:
                logger.error("Failed to fetch event %s: %s", pending.meeting_id, exc)

        organizer = self._extract_organizer(raw_event)
        participants = self._extract_participants(raw_event)

        context = MeetingContext(
            meeting_id=pending.meeting_id,
            title=pending.title,
            date=pending.date,
            organizer=organizer,
            participants=participants,
            source=pending.source,
            description=raw_event.get("body", {}).get("content"),
        )

        # Fetch supplementary content via Graph
        if self._graph and pending.has_notes:
            context.facilitator_notes = self._fetch_loop_notes(pending.meeting_id)

        if self._graph and pending.has_transcript:
            context.transcript = self._fetch_transcript(pending.meeting_id)

        if self._graph and pending.has_chat:
            context.chat_messages = self._fetch_chat(pending.meeting_id)

        context.normalised_body = self._normalise(context)
        logger.info(
            "Ingestion complete for %s — notes=%s transcript=%s chat=%s",
            pending.meeting_id,
            bool(context.facilitator_notes),
            bool(context.transcript),
            bool(context.chat_messages),
        )
        return context

    def ingest_from_files(
        self,
        meeting_id: str,
        title: str,
        date_str: str,
        notes_path: str | None = None,
        transcript_path: str | None = None,
        chat_path: str | None = None,
    ) -> MeetingContext:
        """Offline ingestion — load content from local files (dev/test mode)."""
        from datetime import datetime

        context = MeetingContext(
            meeting_id=meeting_id,
            title=title,
            date=datetime.fromisoformat(date_str),
            organizer=MeetingParticipant(name="Unknown"),
        )
        if notes_path:
            context.facilitator_notes = self._read_file(notes_path)
        if transcript_path:
            context.transcript = self._read_file(transcript_path)
        if chat_path:
            context.chat_messages = self._read_file(chat_path)
        context.normalised_body = self._normalise(context)
        return context

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_loop_notes(self, meeting_id: str) -> str | None:
        try:
            return self._graph.get_loop_notes(meeting_id)
        except Exception as exc:
            logger.warning("Could not fetch Loop notes for %s: %s", meeting_id, exc)
            return None

    def _fetch_transcript(self, meeting_id: str) -> str | None:
        try:
            return self._graph.get_transcript(meeting_id)
        except Exception as exc:
            logger.warning("Could not fetch transcript for %s: %s", meeting_id, exc)
            return None

    def _fetch_chat(self, meeting_id: str) -> str | None:
        try:
            return self._graph.get_chat_messages(meeting_id)
        except Exception as exc:
            logger.warning("Could not fetch chat for %s: %s", meeting_id, exc)
            return None

    @staticmethod
    def _extract_organizer(event: dict) -> MeetingParticipant:
        org = event.get("organizer", {}).get("emailAddress", {})
        return MeetingParticipant(
            name=org.get("name", "Unknown"),
            email=org.get("address"),
        )

    @staticmethod
    def _extract_participants(event: dict) -> list[MeetingParticipant]:
        attendees = event.get("attendees", [])
        return [
            MeetingParticipant(
                name=a.get("emailAddress", {}).get("name", ""),
                email=a.get("emailAddress", {}).get("address"),
                role=a.get("type", "attendee"),
            )
            for a in attendees
        ]

    @staticmethod
    def _normalise(context: MeetingContext) -> str:
        """
        Concatenate available sources in priority order and strip artefacts
        (HTML tags, repeated whitespace, zero-width chars).
        """
        parts: list[str] = []
        if context.facilitator_notes:
            parts.append(context.facilitator_notes)
        if context.transcript:
            parts.append(context.transcript)
        if context.chat_messages:
            parts.append(context.chat_messages)
        if context.description:
            parts.append(context.description)

        combined = "\n\n".join(parts)
        # Strip HTML tags
        combined = re.sub(r"<[^>]+>", " ", combined)
        # Strip CSS rule blocks embedded in Loop/Teams page exports
        # e.g. "ol {margin-bottom:0in;}" or "ol.scriptor-... {counter-reset: section;}"
        combined = re.sub(r"(?:ol|ul|li)[^{\n]*\{[^}]*\}", " ", combined)
        # Collapse whitespace
        combined = re.sub(r"[ \t]+", " ", combined)
        combined = re.sub(r"\n{3,}", "\n\n", combined)
        return combined.strip()

    @staticmethod
    def _read_file(path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()
