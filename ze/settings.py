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

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Config paths ─────────────────────────────────────────────────────────
    config_dir: Path = _ROOT / "config"

    # ── Derived config (loaded from YAML, not env) ────────────────────────────

    @property
    def capabilities_path(self) -> Path:
        return self.config_dir / "capabilities.yaml"

    @property
    def capabilities_config(self) -> dict[str, Any]:
        return _load_yaml(self.capabilities_path)

    @property
    def models_config(self) -> dict[str, Any]:
        return _load_yaml(self.config_dir / "models.yaml")

    @property
    def routing_config(self) -> dict[str, Any]:
        return self.models_config.get("routing", {})

    @property
    def agent_configs(self) -> dict[str, dict[str, Any]]:
        agents_dir = self.config_dir / "agents"
        return {p.stem: _load_yaml(p) for p in sorted(agents_dir.glob("*.yaml"))}

    @property
    def persona_config(self) -> dict[str, Any]:
        path = self.config_dir / "persona.yaml"
        if path.exists():
            return _load_yaml(path)
        return {"traits": ["direct", "warm", "concise"], "verbosity": "concise", "custom_instructions": ""}


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
