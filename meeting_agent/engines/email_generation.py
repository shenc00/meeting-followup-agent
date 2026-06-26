from __future__ import annotations

import logging

from meeting_agent.config import Settings
from meeting_agent.models.action import ActionItem
from meeting_agent.models.email import DraftEmailPackage, EmailMode, EmailType
from meeting_agent.models.followup import FollowUpPlan
from meeting_agent.models.meeting import MeetingContext
from meeting_agent.skills.email_drafting import EmailDraftingSkill

logger = logging.getLogger(__name__)


class EmailGenerationEngine:
    """
    MODULE 6 — Generate complete business-ready email drafts.

    For each action that requires an email:
      - Generates an initial email
      - Optionally generates a reminder and escalation template
      - Publishes drafts to Outlook via Graph (mode-dependent)
    """

    def __init__(self, settings: Settings, graph_client=None) -> None:
        self.settings = settings
        self._skill = EmailDraftingSkill(settings)
        self._graph = graph_client
        self._mode = EmailMode(settings.email_mode)

    def generate(
        self,
        actions: list[ActionItem],
        plans: list[FollowUpPlan],
        context: MeetingContext,
    ) -> list[DraftEmailPackage]:
        plan_map = {p.action_id: p for p in plans}
        drafts: list[DraftEmailPackage] = []

        for action in actions:
            plan = plan_map.get(action.action_id)
            if plan is None or not plan.email_required:
                continue

            for email_type in [EmailType.INITIAL, EmailType.REMINDER, EmailType.ESCALATION]:
                try:
                    draft = self._skill.run(
                        action=action,
                        context=context,
                        email_type=email_type,
                        mode=self._mode,
                    )
                    if email_type == EmailType.INITIAL:
                        self._handle_draft(draft)
                    drafts.append(draft)
                    action.related_email_ids.append(draft.email_id)
                    logger.info(
                        "Generated %s email for action %s",
                        email_type.value,
                        action.action_id[:8],
                    )
                except Exception as exc:
                    logger.error(
                        "Email generation failed (%s) for action %s: %s",
                        email_type.value,
                        action.action_id[:8],
                        exc,
                    )

        return drafts

    def _handle_draft(self, draft: DraftEmailPackage) -> None:
        """Push the initial draft to Outlook based on the configured mode."""
        if self._graph is None:
            logger.debug("No Graph client — draft stored locally only")
            return

        if self._mode == EmailMode.DRAFT_ONLY:
            graph_id = self._graph.create_mail_draft(draft)
            draft.graph_draft_id = graph_id
            logger.info("Outlook draft created: %s", graph_id)

        elif self._mode == EmailMode.DRAFT_AND_APPROVAL:
            graph_id = self._graph.create_mail_draft(draft)
            draft.graph_draft_id = graph_id
            logger.info("Outlook draft created (awaiting approval): %s", graph_id)

        elif self._mode == EmailMode.AUTO_SEND:
            self._graph.send_mail(draft)
            logger.info("Email auto-sent for action %s", draft.action_id[:8])
