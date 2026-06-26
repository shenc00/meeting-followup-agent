from __future__ import annotations

import logging

from tinydb import Query, TinyDB
from tinydb.storages import JSONStorage
from tinydb_serialization import SerializationMiddleware
from tinydb_serialization.serializers import DateTimeSerializer

from meeting_agent.config import Settings
from meeting_agent.engines.task_management import TaskManagementEngine
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.models.task import Task
from meeting_agent.skills.historical_context import HistoricalContextSkill

logger = logging.getLogger(__name__)


class MeetingMemoryEngine:
    """
    MODULE 10 — Maintain historical context across meetings.

    Stores processed MeetingContext records and provides cross-meeting linking
    (repeated topics, open commitments, missed actions) via HistoricalContextSkill.
    """

    def __init__(self, settings: Settings, task_engine: TaskManagementEngine) -> None:
        self.settings = settings
        self._task_engine = task_engine
        self._skill = HistoricalContextSkill(settings)

        serialization = SerializationMiddleware(JSONStorage)
        serialization.register_serializer(DateTimeSerializer(), "TinyDate")
        self._db = TinyDB(settings.storage.meeting_db_path, storage=serialization)
        self._meeting_table = self._db.table("meetings")

    def store_meeting(self, context: MeetingContext) -> None:
        """Persist a processed meeting context."""
        self._meeting_table.upsert(
            context.model_dump(mode="json"),
            Query().meeting_id == context.meeting_id,
        )
        logger.debug("Meeting %s stored in memory", context.meeting_id)

    def find_historical_links(self, context: MeetingContext) -> list[dict]:
        """
        Cross-reference the current meeting against historical open tasks and
        return a list of connection records for operator review.
        """
        open_tasks: list[Task] = self._task_engine.get_open()
        if not open_tasks:
            return []

        links = self._skill.run(context=context, open_tasks=open_tasks)
        logger.info(
            "Found %d historical link(s) for meeting %s",
            len(links),
            context.meeting_id,
        )
        return links

    def get_previous_meetings(self, limit: int = 20) -> list[dict]:
        """Return the most recent `limit` processed meetings."""
        rows = self._meeting_table.all()
        rows.sort(key=lambda r: r.get("date", ""), reverse=True)
        return rows[:limit]
