from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).parent.parent  # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenRouter ────────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "https://github.com/ze"
    openrouter_title: str = "Ze Personal Assistant"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql://ze:ze@localhost:5432/ze"
    database_url_sync: str = "postgresql+psycopg2://ze:ze@localhost:5432/ze"

    # ── Research ──────────────────────────────────────────────────────────────
    tavily_api_key: str = ""

    # ── API ───────────────────────────────────────────────────────────────────
    ze_api_key: str = "change-me"
    confirm_timeout_seconds: int = 900
    session_inactivity_minutes: int = 30

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_chat_id: int = 0
    public_url: str = ""

    # ── Google OAuth2 ────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    timezone: str = "UTC"

    # ── Workflow ──────────────────────────────────────────────────────────────
    scheduler_enabled: bool = True
    workflow_plan_model: str = "anthropic/claude-haiku-4-5-20251001"
    workflow_verify_model: str = "anthropic/claude-haiku-4-5-20251001"

    # ── Memory consolidation ──────────────────────────────────────────────────
    consolidation_enabled: bool = True

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Config paths ─────────────────────────────────────────────────────────
    config_dir: Path = _ROOT / "config"

    # ── Derived config (loaded from YAML, not env) ────────────────────────────

    @property
    def capabilities_path(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def models_config(self) -> dict[str, Any]:
        return _load_yaml(self.config_dir / "config.yaml")

    @property
    def routing_config(self) -> dict[str, Any]:
        return self.models_config.get("routing", {})

    @property
    def consolidation_config(self) -> dict[str, Any]:
        return self.models_config.get("memory", {}).get("consolidation", {})

    @property
    def proactive_config(self) -> dict[str, Any]:
        return self.models_config.get("proactive", {})

    @property
    def agent_configs(self) -> dict[str, dict[str, Any]]:
        return _load_yaml(self.config_dir / "config.yaml").get("agents", {})

    @property
    def persona_config(self) -> dict[str, Any]:
        cfg = _load_yaml(self.config_dir / "config.yaml")
        return cfg.get("persona", {"traits": ["direct", "warm", "concise"], "verbosity": "concise", "custom_instructions": ""})


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
