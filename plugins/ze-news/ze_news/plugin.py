from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg
from sentence_transformers import SentenceTransformer

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_agents.plugin import ZePlugin
from ze_agents.settings import Settings as CoreSettings
from ze_news.onboarding import NewsOnboardingProvider

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

        self._salience_cfg: dict | None = None
        self._news_signal_source: Any = None
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
        signals_cfg = settings.config.get("memory", {}).get("signals", {})
        self._force_ingest_sources: list[str] = signals_cfg.get("force_ingest_sources", [])
        salience_raw = settings.config.get("correlation", {}).get("salience", {})
        self._salience_cfg = salience_raw if salience_raw else None

        from ze_news.signals import NewsSignalSource

        self._news_signal_source = NewsSignalSource()
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
            force_ingest_sources=self._force_ingest_sources,
            signal_source=self._news_signal_source,
        )

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    def rest_stores(self) -> dict[str, Any]:
        if self._store is None:
            return {}
        return {"news_store": self._store}

    def agent_deps(self, accumulated: dict) -> dict:
        if self._store is None:
            return {}
        from ze_news.jobs.fetch import NewsFetchJob
        from ze_news.store import NewsStore

        return {NewsStore: self._store, NewsFetchJob: self._fetch_job}

    def configurable_services(self) -> dict[str, Any]:
        if self._store is None:
            return {}
        return {"news_store": self._store}

    def memory_policies(self) -> dict:
        from ze_memory.policies import ResearchPolicy

        return {"news": ResearchPolicy()}

    def onboarding(self) -> NewsOnboardingProvider | None:
        if not self._enabled:
            return None
        return NewsOnboardingProvider()

    def signal_sources(self) -> list:
        if self._news_signal_source is None:
            return []
        return [self._news_signal_source]

    def agent_module_paths(self) -> list[str]:
        if not self._enabled:
            return []
        return ["ze_news.agents.agent"]

    async def startup(self, container: Any) -> None:
        if self._fetch_job is None or self._store is None:
            return

        memory_store = getattr(container, "memory_store", None)
        if memory_store is not None:
            self._fetch_job._memory_store = memory_store

        if memory_store is not None and self._salience_cfg is not None:
            self._fetch_job._admission_gate = self._build_admission_gate(
                memory_store, container
            )

        container.proactive_scheduler.register(
            self._fetch_job, cron=self._fetch_cron
        )
        log.info(
            "news_fetch_scheduled",
            cron=self._fetch_cron,
            sources=self._source_count,
        )

    def _build_admission_gate(self, memory_store: Any, container: Any) -> Any:
        from ze_memory.admission import AdmissionGate
        from ze_memory.relevance import RelevanceModel

        goal_provider = None
        for plugin in getattr(container, "plugins", []):
            gs = getattr(plugin, "goal_store", None)
            if gs is not None:
                goal_provider = gs
                break

        rel_cfg = self._salience_cfg.get("relevance", {})
        relevance_model = RelevanceModel(
            memory_store=memory_store,
            goal_provider=goal_provider,
            episode_lookback_days=int(rel_cfg.get("episode_lookback_days", 30)),
            cache_ttl_minutes=int(rel_cfg.get("cache_ttl_minutes", 30)),
        )

        adm_cfg = self._salience_cfg.get("admission", {})
        return AdmissionGate(
            relevance_model=relevance_model,
            memory_store=memory_store,
            tau_admit=float(adm_cfg.get("tau_admit", 0.55)),
            tau_watch=float(adm_cfg.get("tau_watch", 0.35)),
            w_relevance=float(adm_cfg.get("w_relevance", 0.7)),
            w_magnitude=float(adm_cfg.get("w_magnitude", 0.3)),
            watch_buffer_ttl_hours=float(adm_cfg.get("watch_buffer_ttl_hours", 48)),
            dry_run=bool(self._salience_cfg.get("dry_run", False)),
        )
