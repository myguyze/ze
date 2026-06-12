from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg
from sentence_transformers import SentenceTransformer

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_agents.plugin import ZePlugin
from ze_agents.settings import Settings as CoreSettings

log = get_logger(__name__)


class NewsPlugin(ZePlugin):
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        settings: CoreSettings,
        openrouter_client: LLMClient,
    ) -> None:
        from ze_news.store import NewsStore
        from ze_news.registry import build_registry
        from ze_news.jobs.fetch import NewsFetchJob
        from ze_news.types import SourceConfig

        self._pool = pool
        news_cfg = settings.config.get("news", {})
        self._enabled = bool(news_cfg.get("enabled", True) and news_cfg.get("sources"))
        self._store: NewsStore | None = None
        self._fetch_job: NewsFetchJob | None = None
        self._fetch_cron: str = news_cfg.get("fetch_schedule", "*/30 * * * *")
        self._source_count: int = 0

        if not self._enabled:
            return

        source_configs = [
            SourceConfig(
                key=s["key"],
                type=s["type"],
                url=s["url"],
                tags=s.get("tags", []),
            )
            for s in news_cfg["sources"]
        ]
        registry = build_registry(source_configs)
        self._store = NewsStore(pool=pool, embedder=embedder)
        self._source_count = len(source_configs)

        credibility_cfg = news_cfg.get("credibility", {})
        self._fetch_job = NewsFetchJob(
            registry=registry,
            store=self._store,
            retention_days=int(news_cfg.get("retention_days", 7)),
            client=openrouter_client if credibility_cfg.get("enabled", False) else None,
            credibility_enabled=credibility_cfg.get("enabled", False),
            credibility_llm_enabled=credibility_cfg.get("llm_scoring", True),
            credibility_model=credibility_cfg.get("model", "openai/gpt-4o-mini"),
            min_fetch_interval_minutes=int(
                news_cfg.get("min_fetch_interval_minutes", 30)
            ),
        )

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    def configurable_services(self) -> dict[str, Any]:
        if self._store is None:
            return {}
        return {"news_store": self._store}

    def agent_module_paths(self) -> list[str]:
        if not self._enabled:
            return []
        return ["ze_news.agents.agent"]

    async def startup(self, container: Any) -> None:
        if self._fetch_job is None or self._store is None:
            return
        container.proactive_scheduler.register(
            self._fetch_job, cron=self._fetch_cron
        )
        log.info(
            "news_fetch_scheduled",
            cron=self._fetch_cron,
            sources=self._source_count,
        )
