from __future__ import annotations

from pathlib import Path
from typing import Any

from ze_core.plugin import ZePlugin
from ze_news.jobs.fetch import NewsFetchJob
from ze_news.registry import SourceRegistry
from ze_news.store import NewsStore


class NewsPlugin(ZePlugin):
    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        fetch_job: NewsFetchJob,
    ) -> None:
        self._registry = registry
        self._store = store
        self._fetch_job = fetch_job

    def agents(self) -> list:
        from ze_news.agents.agent import NewsAgent
        return [NewsAgent]

    def jobs(self) -> list:
        return [self._fetch_job]

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    def configurable_services(self) -> dict[str, Any]:
        return {"news_store": self._store}

    def agent_module_paths(self) -> list[str]:
        return ["ze_news.agents.agent"]
