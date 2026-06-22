from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tests.support.repo_paths import CONFIG_DIR


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


@dataclass
class TestSettings:
    openrouter_api_key: str = "test-key"
    database_url: str = "postgresql://ze:ze@localhost:5432/ze"
    database_url_sync: str = "postgresql+psycopg2://ze:ze@localhost:5432/ze"
    config_dir: Path = field(default_factory=lambda: CONFIG_DIR)
    timezone: str = "UTC"

    @property
    def config(self) -> dict:
        return _load_yaml(self.config_dir / "config.yaml")

    @property
    def routing_config(self) -> dict:
        return self.config.get("routing", {})

    @property
    def proactive_config(self) -> dict:
        return self.config.get("proactive", {})


def make_settings(**overrides) -> TestSettings:
    return TestSettings(**overrides)
