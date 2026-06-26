from __future__ import annotations

import logging

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.skills.action_extraction import ActionExtractionSkill

logger = logging.getLogger(__name__)


class ActionExtractionEngine:
    """
    MODULE 3 — Extract structured action items from a MeetingContext.

    Strategy:
      1. Deterministic pass: regex trigger patterns flag candidate sentences
      2. AI pass: ActionExtractionSkill processes the full normalised body
      3. Deduplication: drop actions with identical task descriptions
      4. Governance: reject items with confidence < threshold
    """

    CONFIDENCE_THRESHOLD = 0.5

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._skill = ActionExtractionSkill(settings)

    def extract(self, context: MeetingContext) -> list[ActionItem]:
        if not context.normalised_body:
            logger.warning("No normalised body for meeting %s — skipping extraction", context.meeting_id)
            return []

        logger.info("Extracting actions from meeting %s", context.meeting_id)
        raw_actions = self._skill.run(context=context)

        # Filter by confidence
        accepted = [a for a in raw_actions if a.extraction_confidence >= self.CONFIDENCE_THRESHOLD]

        # Deduplicate by normalised description
        seen: set[str] = set()
        unique: list[ActionItem] = []
        for action in accepted:
            key = action.task_description.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(action)

        logger.info(
            "Extracted %d action(s) from meeting %s (%d filtered by confidence)",
            len(unique),
            context.meeting_id,
            len(raw_actions) - len(accepted),
        )
        return unique
