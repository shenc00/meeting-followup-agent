from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class PrimaryUser(BaseModel):
    name: str = "Sally"
    email: str = "sally@example.com"


class GraphConfig(BaseModel):
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = Field(default_factory=lambda: [
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "https://graph.microsoft.com/OnlineMeetings.ReadWrite",
        "https://graph.microsoft.com/Chat.Read",
    ])
    token_cache_path: str = "token_cache.bin"


class LLMConfig(BaseModel):
    provider: str = "azure_openai"
    model: str = "gpt-4o"
    api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2024-02-01"
    azure_deployment: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096


class ReminderConfig(BaseModel):
    no_response_days: int = 5
    escalation_days: int = 14
    daily_summary: bool = True
    weekly_summary: bool = True


class StorageConfig(BaseModel):
    db_path: str = "data/actions.json"
    meeting_db_path: str = "data/meetings.json"


class Settings(BaseModel):
    primary_user: PrimaryUser = Field(default_factory=PrimaryUser)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    email_mode: str = "draft"
    scheduling_mode: str = "draft"
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    log_level: str = "INFO"


def load_settings(config_path: Optional[str] = None) -> Settings:
    """
    Load settings from YAML file, with environment variable overrides.

    Priority (highest first):
      1. Environment variables (OPENAI_API_KEY, GRAPH_CLIENT_SECRET, etc.)
      2. config/config.yaml (or path supplied)
      3. Built-in defaults
    """
    path = config_path or os.environ.get("MEETING_AGENT_CONFIG", "config/config.yaml")

    raw: dict = {}
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        logging.getLogger(__name__).warning(
            "Config file not found at '%s' — using defaults", path
        )

    # Inject secrets from environment variables
    if "llm" not in raw:
        raw["llm"] = {}
    if "graph" not in raw:
        raw["graph"] = {}

    raw["llm"]["api_key"] = os.environ.get("OPENAI_API_KEY", raw["llm"].get("api_key", ""))
    raw["graph"]["client_secret"] = os.environ.get(
        "GRAPH_CLIENT_SECRET", raw["graph"].get("client_secret", "")
    )

    settings = Settings(**raw)

    # Ensure storage directories exist
    for db_path in [settings.storage.db_path, settings.storage.meeting_db_path]:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    return settings
