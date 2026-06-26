from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from tinydb import Query, TinyDB
from tinydb.storages import JSONStorage
from tinydb_serialization import SerializationMiddleware
from tinydb_serialization.serializers import DateTimeSerializer

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem, ActionStatus
from meeting_agent.models.task import Task

logger = logging.getLogger(__name__)


def _build_db(path: str) -> TinyDB:
    serialization = SerializationMiddleware(JSONStorage)
    serialization.register_serializer(DateTimeSerializer(), "TinyDate")
    return TinyDB(path, storage=serialization)


class TaskManagementEngine:
    """
    MODULE 8 — Persistent, queryable action repository.

    Wraps TinyDB for lightweight file-based storage.  In production this could
    be swapped for a SQL backend without changing the public interface.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db = _build_db(settings.storage.db_path)
        self._table = self._db.table("tasks")

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_from_action(self, action: ActionItem, meeting_id: str) -> Task:
        """Create or update a Task from an extracted ActionItem."""
        existing = self.get_by_action_id(action.action_id)
        if existing:
            existing.updated_at = datetime.utcnow()
            existing.status = action.status
            self._table.update(
                existing.model_dump(mode="json"),
                Query().action_id == action.action_id,
            )
            return existing

        task = Task(
            action_id=action.action_id,
            meeting_id=meeting_id,
            description=action.task_description,
            raw_evidence=action.raw_statement,
            owner=action.assigned_to,
            owner_email=action.assigned_to_email,
            due_date=action.due_date,
            classification=action.classification,
            priority=action.priority,
            status=action.status,
            related_email_ids=action.related_email_ids,
            related_meeting_request_ids=action.related_meeting_request_ids,
        )
        self._table.insert(task.model_dump(mode="json"))
        logger.debug("Task created: %s", task.task_id[:8])
        return task

    def update_status(self, task_id: str, status: ActionStatus) -> bool:
        Q = Query()
        updated = self._table.update(
            {"status": status.value, "updated_at": datetime.utcnow().isoformat()},
            Q.task_id == task_id,
        )
        return bool(updated)

    def add_note(self, task_id: str, note: str) -> bool:
        task = self.get_by_task_id(task_id)
        if not task:
            return False
        task.notes.append(note)
        task.updated_at = datetime.utcnow()
        Q = Query()
        self._table.update(task.model_dump(mode="json"), Q.task_id == task_id)
        return True

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_task_id(self, task_id: str) -> Optional[Task]:
        Q = Query()
        row = self._table.get(Q.task_id == task_id)
        return Task(**row) if row else None

    def get_by_action_id(self, action_id: str) -> Optional[Task]:
        Q = Query()
        row = self._table.get(Q.action_id == action_id)
        return Task(**row) if row else None

    def get_open(self) -> list[Task]:
        Q = Query()
        rows = self._table.search(
            Q.status.one_of([
                ActionStatus.OPEN.value,
                ActionStatus.DRAFTED.value,
                ActionStatus.WAITING_RESPONSE.value,
                ActionStatus.IN_PROGRESS.value,
                ActionStatus.BLOCKED.value,
            ])
        )
        return [Task(**r) for r in rows]

    def get_by_meeting(self, meeting_id: str) -> list[Task]:
        Q = Query()
        rows = self._table.search(Q.meeting_id == meeting_id)
        return [Task(**r) for r in rows]

    def get_overdue(self) -> list[Task]:
        return [t for t in self.get_open() if t.is_overdue()]

    def get_all(self) -> list[Task]:
        return [Task(**r) for r in self._table.all()]
