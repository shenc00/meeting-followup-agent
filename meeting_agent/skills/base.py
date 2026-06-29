from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from openai import AzureOpenAI, OpenAI

from meeting_agent.config import Settings

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """
    Base class for all AI skills.

    Concrete skills implement `_build_prompt` and `_parse_response`.
    The `run` method handles the LLM call, retry logic, and logging.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = self._build_client()

    def _build_client(self) -> AzureOpenAI | OpenAI:
        cfg = self.settings.llm
        if cfg.provider == "azure_openai":
            return AzureOpenAI(
                api_key=cfg.api_key,
                azure_endpoint=cfg.azure_endpoint,
                api_version=cfg.azure_api_version,
            )
        return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url or None)

    @property
    def _model(self) -> str:
        cfg = self.settings.llm
        if cfg.provider == "azure_openai":
            return cfg.azure_deployment
        return cfg.model

    @abstractmethod
    def _build_messages(self, **kwargs: Any) -> list[dict[str, str]]:
        """Return the messages list for the chat completion call."""

    @abstractmethod
    def _parse_response(self, raw: str) -> Any:
        """Parse and validate the raw LLM text response."""

    def run(self, **kwargs: Any) -> Any:
        messages = self._build_messages(**kwargs)
        logger.debug("Calling LLM skill %s", self.__class__.__name__)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self.settings.llm.temperature,
            max_tokens=self.settings.llm.max_tokens,
        )
        raw = response.choices[0].message.content or ""
        return self._parse_response(raw)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Strip markdown fences then parse JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
