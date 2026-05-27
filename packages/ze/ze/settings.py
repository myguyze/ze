from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).parent.parent  # packages/ze/


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

    # ── Browser sidecar ───────────────────────────────────────────────────────
    browser_service_url: str = "http://ze-browser.internal:8080"
    browser_timeout_seconds: int = 20
    browser_max_text_chars: int = 8000
    browser_delay_ms: int = 2000

    # ── Prospecting ───────────────────────────────────────────────────────────
    prospecting_max_iterations: int = 15
    prospecting_max_loop_tokens: int = 24_000
    prospecting_stale_timeout_minutes: int = 60

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = ""

    # ── Config paths ─────────────────────────────────────────────────────────
    config_dir: Path = _ROOT / "config"

    # ── Derived config (loaded from YAML, not env) ────────────────────────────

    @property
    def capabilities_path(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def config(self) -> dict[str, Any]:
        return _load_yaml(self.config_dir / "config.yaml")

    # Keep alias so external tooling that reads models_config still works.
    @property
    def models_config(self) -> dict[str, Any]:
        return self.config

    @property
    def routing_config(self) -> dict[str, Any]:
        """Routing thresholds live in ze-core defaults; optional YAML overrides only."""
        return self.config.get("routing", {})

    @property
    def consolidation_config(self) -> dict[str, Any]:
        return self.config.get("memory", {}).get("consolidation", {})

    @property
    def contacts_config(self) -> dict[str, Any]:
        return self.config.get("contacts", {})

    @property
    def profile_config(self) -> dict[str, Any]:
        return self.config.get("memory", {}).get("profile", {})

    @property
    def memory_insights_config(self) -> dict[str, Any]:
        return self.config.get("memory", {}).get("insights", {})

    @property
    def proactive_config(self) -> dict[str, Any]:
        return self.config.get("proactive", {})

    @property
    def agent_configs(self) -> dict[str, dict[str, Any]]:
        return self.config.get("agents", {})

    @property
    def persona_config(self) -> dict[str, Any]:
        cfg = self.config.get("persona", {})
        if cfg:
            return cfg
        # Absolute fallback if persona: block is missing entirely.
        return {
            "profile": "default",
            "locale": "en",
            "profiles": {
                "default": {
                    "traits": ["direct", "warm", "concise"],
                    "verbosity": "concise",
                    "custom_instructions": "",
                    "dials": {"humor": 0.3, "directness": 0.9, "formality": 0.2, "depth": 0.5},
                }
            },
        }

    def active_profile(self) -> dict[str, Any]:
        """Return the YAML-default active profile dict (no DB override)."""
        cfg = self.persona_config
        profiles = cfg.get("profiles", {})
        if profiles:
            name = cfg.get("profile", "default")
            return profiles.get(name) or next(iter(profiles.values()))
        # Legacy flat format: wrap as a profile dict.
        return {
            "traits": cfg.get("traits", ["direct", "warm", "concise"]),
            "verbosity": cfg.get("verbosity", "concise"),
            "custom_instructions": cfg.get("custom_instructions", ""),
            "dials": {},
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
