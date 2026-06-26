from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from ze_agents.settings import Settings as CoreSettings
from ze_memory.bootstrap import consolidation_enabled

_ROOT = Path(__file__).parent.parent  # apps/ze-api/


class ZeApiSettings(BaseSettings):
    """Ze API shell settings (env + YAML). Domain flags live in package YAML helpers."""
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
    auto_migrate: bool = False
    auto_seed_dev_data: bool = False

    # ── API ───────────────────────────────────────────────────────────────────
    ze_api_key: str = "change-me"
    cors_origins: str = "*"
    confirm_timeout_seconds: int = 900
    session_inactivity_minutes: int = 30

    # ── Browser sidecar ───────────────────────────────────────────────────────
    browser_service_url: str = "http://ze-browser.internal:8080"
    browser_timeout_seconds: int = 20
    browser_max_text_chars: int = 8000
    browser_delay_ms: int = 2000

    # ── Agent harness ─────────────────────────────────────────────────────────
    max_tool_calls_per_turn: int = 20

    # ── Public URL (used for webhook registration) ────────────────────────────
    public_url: str = ""

    # ── Gmail push (Pub/Sub topic for push notifications) ─────────────────────
    gmail_pubsub_topic: str = ""

    # ── Ntfy push notifications ───────────────────────────────────────────────
    ntfy_base_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = ""
    log_dev: bool = False

    # ── Config paths ─────────────────────────────────────────────────────────
    config_dir: Path = _ROOT / "config"

    # ── Derived config (loaded from YAML, not env) ────────────────────────────

    @property
    def capabilities_path(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def config(self) -> dict[str, Any]:
        return _load_yaml(self.config_dir / "config.yaml")

    @property
    def routing_config(self) -> dict[str, Any]:
        """Routing thresholds live in ze-core defaults; optional YAML overrides only."""
        return self.config.get("routing", {})

    @property
    def consolidation_config(self) -> dict[str, Any]:
        """Legacy YAML overrides; thresholds default in ze-core."""
        return self.config.get("memory", {}).get("consolidation", {})

    @property
    def graph_config(self) -> dict[str, Any]:
        return self.config.get("memory", {}).get("graph", {})

    @property
    def contacts_config(self) -> dict[str, Any]:
        return self.config.get("contacts", {})

    @property
    def profile_config(self) -> dict[str, Any]:
        return self.config.get("memory", {}).get("profile", {})

    @property
    def memory_insights_config(self) -> dict[str, Any]:
        """Insight engine tuning (lives under proactive.insights in config.yaml)."""
        return self.proactive_config.get("insights", {})

    @property
    def proactive_config(self) -> dict[str, Any]:
        return self.config.get("proactive", {})

    @property
    def dream_config(self) -> dict[str, Any]:
        return self.config.get("dream", {})

    @property
    def persona_path(self) -> Path:
        return self.config_dir / "persona.yaml"

    @property
    def persona_config(self) -> dict[str, Any]:
        if self.persona_path.exists():
            return _load_yaml(self.persona_path)
        # Legacy: persona block embedded in config.yaml
        cfg = self.config.get("persona", {})
        if cfg:
            return cfg
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

    def to_core_settings(self) -> CoreSettings:
        """Map to ze-core Settings for framework container helpers."""
        tz = self.config.get("timezone") or os.environ.get("TIMEZONE", "UTC")
        return CoreSettings(
            openrouter_api_key=self.openrouter_api_key,
            database_url=self.database_url,
            database_url_sync=self.database_url_sync,
            openrouter_base_url=self.openrouter_base_url,
            session_inactivity_minutes=self.session_inactivity_minutes,
            consolidation_enabled=consolidation_enabled(self),
            auto_migrate=False,
            log_level=self.log_level,
            timezone=tz,
            config=self.config,
        )


Settings = ZeApiSettings


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> ZeApiSettings:
    return ZeApiSettings()
