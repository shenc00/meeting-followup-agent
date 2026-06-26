from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from meeting_agent.integrations.auth import GraphAuthClient
from meeting_agent.models.email import DraftEmailPackage
from meeting_agent.models.scheduling import MeetingRequest

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """
    Microsoft Graph API client.

    Wraps the REST endpoints used by the meeting agent:
      - Calendar events
      - Online meeting transcripts
      - Teams chat messages
      - Mail (draft / send)
      - Loop / OneNote notes
    """

    def __init__(self, auth: GraphAuthClient, user_email: str) -> None:
        self._auth = auth
        self._user = user_email

    # ── Auth header ───────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{GRAPH_BASE}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> Any:
        url = f"{GRAPH_BASE}{path}"
        resp = requests.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Calendar ──────────────────────────────────────────────────────────────

    def get_recent_calendar_events(self, lookback_hours: int = 24) -> list[dict]:
        start = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
        end = datetime.now(timezone.utc).isoformat()
        result = self._get(
            f"/users/{self._user}/calendarView",
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$select": "id,subject,start,end,organizer,attendees,isOnlineMeeting,body",
                "$top": 50,
            },
        )
        return result.get("value", [])

    def get_event(self, event_id: str) -> dict:
        return self._get(f"/users/{self._user}/events/{event_id}")

    def create_calendar_event(self, request: MeetingRequest) -> tuple[str, Optional[str]]:
        body = {
            "subject": request.subject,
            "body": {"contentType": "Text", "content": "\n".join(request.agenda)},
            "start": {
                "dateTime": (request.proposed_dates[0] if request.proposed_dates else datetime.utcnow()).isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": (
                    (request.proposed_dates[0] if request.proposed_dates else datetime.utcnow())
                    + timedelta(minutes=request.estimated_duration_minutes)
                ).isoformat(),
                "timeZone": "UTC",
            },
            "attendees": [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in request.required_attendees
            ] + [
                {"emailAddress": {"address": email}, "type": "optional"}
                for email in request.optional_attendees
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }
        result = self._post(f"/users/{self._user}/events", body)
        join_url = result.get("onlineMeeting", {}).get("joinUrl")
        return result["id"], join_url

    # ── Mail ──────────────────────────────────────────────────────────────────

    def create_mail_draft(self, draft: DraftEmailPackage) -> str:
        body = {
            "subject": draft.subject,
            "body": {
                "contentType": "HTML" if draft.body_html else "Text",
                "content": draft.body_html or draft.body_plain,
            },
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in draft.recipients_to
            ],
            "ccRecipients": [
                {"emailAddress": {"address": addr}} for addr in draft.recipients_cc
            ],
        }
        result = self._post(f"/users/{self._user}/messages", body)
        return result["id"]

    def send_mail(self, draft: DraftEmailPackage) -> None:
        body = {
            "message": {
                "subject": draft.subject,
                "body": {
                    "contentType": "HTML" if draft.body_html else "Text",
                    "content": draft.body_html or draft.body_plain,
                },
                "toRecipients": [
                    {"emailAddress": {"address": addr}} for addr in draft.recipients_to
                ],
                "ccRecipients": [
                    {"emailAddress": {"address": addr}} for addr in draft.recipients_cc
                ],
            },
            "saveToSentItems": "true",
        }
        self._post(f"/users/{self._user}/sendMail", body)

    # ── Transcripts / Chat ────────────────────────────────────────────────────

    def get_transcript(self, meeting_id: str) -> Optional[str]:
        """
        Retrieve transcript for a Teams online meeting.
        Requires CallRecords.Read.All permission.
        """
        try:
            result = self._get(f"/users/{self._user}/onlineMeetings/{meeting_id}/transcripts")
            transcripts = result.get("value", [])
            if not transcripts:
                return None
            transcript_id = transcripts[0]["id"]
            content = self._get(
                f"/users/{self._user}/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content",
                params={"$format": "text/vtt"},
            )
            return str(content) if content else None
        except Exception as exc:
            logger.warning("Transcript retrieval failed for %s: %s", meeting_id, exc)
            return None

    def get_chat_messages(self, meeting_id: str) -> Optional[str]:
        """Retrieve Teams chat messages associated with a meeting."""
        try:
            result = self._get(f"/users/{self._user}/onlineMeetings/{meeting_id}/meetingAttendanceReport")
            # Simplified — a real implementation would fetch the linked chat thread
            return None
        except Exception as exc:
            logger.warning("Chat retrieval failed for %s: %s", meeting_id, exc)
            return None

    def get_loop_notes(self, meeting_id: str) -> Optional[str]:
        """
        Retrieve Loop / collaborative notes attached to a meeting.
        Loop notes are accessed via the SharePoint/OneDrive API in production.
        """
        logger.debug("Loop notes retrieval not yet implemented for %s", meeting_id)
        return None
