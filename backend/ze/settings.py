from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).parent.parent  # backend/
_REPO_ROOT = _BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
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
    cors_origins: list[str] = ["http://localhost:3000"]
    confirm_timeout_seconds: int = 900

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Config paths ─────────────────────────────────────────────────────────
    config_dir: Path = _BACKEND_ROOT / "config"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ── Derived config (loaded from YAML, not env) ────────────────────────────

    @property
    def capabilities_path(self) -> Path:
        return self.config_dir / "capabilities.yaml"

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


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
