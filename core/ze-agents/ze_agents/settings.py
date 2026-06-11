from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    openrouter_api_key: str
    database_url: str
    database_url_sync: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    session_inactivity_minutes: int = 30
    consolidation_enabled: bool = True
    auto_migrate: bool = False
    log_level: str = "INFO"
    config: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> "Settings":
        loaded_config: dict = {}
        if config_path is not None:
            config_path = Path(config_path)
            if config_path.exists():
                try:
                    import yaml  # type: ignore[import]
                    with open(config_path) as f:
                        loaded_config = yaml.safe_load(f) or {}
                except ImportError as exc:
                    raise ImportError(
                        "PyYAML is required to load config.yaml."
                        " Install it with: pip install pyyaml"
                    ) from exc

        return cls(
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            database_url=os.environ.get("DATABASE_URL", ""),
            database_url_sync=os.environ.get("DATABASE_URL_SYNC", ""),
            openrouter_base_url=os.environ.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            session_inactivity_minutes=int(
                os.environ.get("SESSION_INACTIVITY_MINUTES", "30")
            ),
            consolidation_enabled=(
                os.environ.get("CONSOLIDATION_ENABLED", "true").lower() != "false"
            ),
            auto_migrate=(
                os.environ.get("ZC_AUTO_MIGRATE", "false").lower() == "true"
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            config=loaded_config,
        )
