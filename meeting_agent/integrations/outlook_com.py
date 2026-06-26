from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _import_win32():
    try:
        import win32com.client
        return win32com.client
    except ImportError:
        raise RuntimeError(
            "pywin32 is not installed. Run: pip install pywin32\n"
            "Also run post-install: python Scripts/pywin32_postinstall.py -install"
        )


# Outlook COM constants
_OL_MAIL_ITEM        = 0
_OL_APPOINTMENT_ITEM = 1
_OL_FOLDER_INBOX     = 6
_OL_FOLDER_CALENDAR  = 9
_OL_FOLDER_SENT      = 5


class OutlookCOMClient:
    """
    Local Outlook COM automation — requires no Azure AD permissions.

    Talks directly to the Outlook desktop application already signed in
    on this machine via win32com.  Provides the same interface as GraphClient
    so engines can use either without modification.
    """

    def __init__(self) -> None:
        win32 = _import_win32()
        try:
            self._outlook = win32.Dispatch("Outlook.Application")
            self._ns      = self._outlook.GetNamespace("MAPI")
        except Exception as exc:
            raise RuntimeError(
                f"Could not connect to Outlook. Make sure Outlook is installed and open.\n{exc}"
            )

    # ── Calendar ──────────────────────────────────────────────────────────────

    def get_recent_calendar_events(self, lookback_hours: int = 24) -> list[dict]:
        """Return calendar appointments that ended within `lookback_hours`."""
        calendar = self._ns.GetDefaultFolder(_OL_FOLDER_CALENDAR)
        items    = calendar.Items
        items.Sort("[Start]", True)
        items.IncludeRecurrences = True

        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        results: list[dict] = []

        for item in items:
            try:
                start = item.Start
                if hasattr(start, "strftime"):
                    start_dt = start
                else:
                    from pywintypes import Time as PyTime  # noqa: F401
                    start_dt = datetime(start.year, start.month, start.day,
                                        start.hour, start.minute, start.second)
                if start_dt < cutoff:
                    break
                results.append({
                    "id":              item.EntryID,
                    "subject":         item.Subject,
                    "start":           {"dateTime": start_dt.isoformat()},
                    "end":             {"dateTime": ""},
                    "organizer":       {"emailAddress": {"name": item.Organizer, "address": ""}},
                    "attendees":       self._parse_recipients(item),
                    "isOnlineMeeting": bool(getattr(item, "NetMeetingServer", "")),
                    "body":            {"content": item.Body or ""},
                    "hasTranscript":   False,
                    "hasChat":         False,
                })
            except Exception:
                continue

        logger.info("COM: found %d calendar event(s) in last %dh", len(results), lookback_hours)
        return results

    def get_event(self, entry_id: str) -> dict:
        item = self._ns.GetItemFromID(entry_id)
        return {
            "id":        item.EntryID,
            "subject":   item.Subject,
            "body":      {"content": item.Body or ""},
            "organizer": {"emailAddress": {"name": item.Organizer, "address": ""}},
            "attendees": self._parse_recipients(item),
        }

    def create_calendar_event(self, request) -> tuple[str, Optional[str]]:
        """Create a calendar appointment / Teams meeting invitation."""
        appt = self._outlook.CreateItem(_OL_APPOINTMENT_ITEM)
        appt.Subject  = request.subject
        appt.Body     = "\n".join(request.agenda)
        appt.Duration = request.estimated_duration_minutes

        if request.proposed_dates:
            appt.Start = request.proposed_dates[0].strftime("%Y-%m-%d %H:%M")

        for email in request.required_attendees:
            rec = appt.Recipients.Add(email)
            rec.Type = 1  # olRequired

        for email in request.optional_attendees:
            rec = appt.Recipients.Add(email)
            rec.Type = 2  # olOptional

        appt.Recipients.ResolveAll()

        if request.mode.value == "auto_schedule":
            appt.Send()
            logger.info("COM: calendar event sent — %s", request.subject)
        else:
            appt.Save()
            logger.info("COM: calendar event saved as draft — %s", request.subject)

        return appt.EntryID, None

    # ── Mail ──────────────────────────────────────────────────────────────────

    def create_mail_draft(self, draft) -> str:
        """Save a mail item to Drafts folder and return its EntryID."""
        mail = self._outlook.CreateItem(_OL_MAIL_ITEM)
        mail.Subject = draft.subject
        if draft.body_html:
            mail.HTMLBody = draft.body_html
        else:
            mail.Body = draft.body_plain

        for addr in draft.recipients_to:
            rec = mail.Recipients.Add(addr)
            rec.Type = 1  # olTo

        for addr in draft.recipients_cc:
            rec = mail.Recipients.Add(addr)
            rec.Type = 2  # olCC

        mail.Recipients.ResolveAll()
        mail.Save()
        logger.info("COM: draft saved — %s", draft.subject)
        return mail.EntryID

    def send_mail(self, draft) -> None:
        """Send immediately using the local Outlook profile."""
        mail = self._outlook.CreateItem(_OL_MAIL_ITEM)
        mail.Subject = draft.subject
        if draft.body_html:
            mail.HTMLBody = draft.body_html
        else:
            mail.Body = draft.body_plain

        for addr in draft.recipients_to:
            rec = mail.Recipients.Add(addr)
            rec.Type = 1

        for addr in draft.recipients_cc:
            rec = mail.Recipients.Add(addr)
            rec.Type = 2

        mail.Recipients.ResolveAll()
        mail.Send()
        logger.info("COM: email sent — %s", draft.subject)

    # ── Stubs matching GraphClient interface ──────────────────────────────────

    def get_transcript(self, meeting_id: str) -> Optional[str]:
        logger.debug("COM: transcript not available via local Outlook — use --from-file")
        return None

    def get_chat_messages(self, meeting_id: str) -> Optional[str]:
        logger.debug("COM: chat not available via local Outlook — use --from-file")
        return None

    def get_loop_notes(self, meeting_id: str) -> Optional[str]:
        logger.debug("COM: Loop notes not available via local Outlook — use --from-file")
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_recipients(item) -> list[dict]:
        results = []
        try:
            for r in item.Recipients:
                results.append({
                    "emailAddress": {
                        "name":    r.Name,
                        "address": r.Address or "",
                    },
                    "type": "attendee",
                })
        except Exception:
            pass
        return results
