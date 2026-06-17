from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ze_agents.logging import get_logger
from ze_sdk.proactive import proactive_job
from ze_news.registry import SourceRegistry
from ze_news.store import NewsStore
from ze_news.types import Article

if TYPE_CHECKING:
    from ze_core.openrouter.client import OpenRouterClient

log = get_logger(__name__)


@proactive_job
class NewsFetchJob:
    job_id = "news_fetch"

    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        retention_days: int = 7,
        client: "OpenRouterClient | None" = None,
        credibility_enabled: bool = False,
        credibility_llm_enabled: bool = True,
        credibility_model: str = "openai/gpt-4o-mini",
        min_fetch_interval_minutes: int = 30,
        memory_store: Any = None,
        force_ingest_sources: list[str] | None = None,
        admission_gate: Any = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._retention_days = retention_days
        self._client = client
        self._credibility_enabled = credibility_enabled
        self._credibility_llm_enabled = credibility_llm_enabled
        self._credibility_model = credibility_model
        self._min_fetch_interval_minutes = min_fetch_interval_minutes
        self._memory_store = memory_store
        self._force_ingest_sources: list[str] = force_ingest_sources or []
        self._admission_gate = admission_gate

    async def run(self, *, force: bool = False) -> None:
        now = datetime.now(timezone.utc)
        for source in self._registry.all():
            if not force and await self._should_skip_source(source.key, now):
                continue

            articles = await source.fetch(limit=50)
            if not articles:
                log.info("news_fetch_empty", source=source.key)
                continue
            new_articles = await self._store.upsert(articles)
            log.info(
                "news_fetch_done",
                source=source.key,
                fetched=len(articles),
                new=len(new_articles),
            )

            if new_articles and self._credibility_enabled and self._client is not None:
                asyncio.create_task(self._score_new_articles(new_articles))

            should_emit = new_articles and self._memory_store is not None
            if should_emit and source.key in self._force_ingest_sources:
                asyncio.create_task(self._emit_signals(new_articles, bypass_gate=True))
            elif should_emit and self._admission_gate is not None:
                asyncio.create_task(self._emit_signals(new_articles, bypass_gate=False))

        pruned = await self._store.prune(older_than_days=self._retention_days)
        if pruned:
            log.info("news_prune_done", pruned=pruned)

    async def _should_skip_source(self, source_key: str, now: datetime) -> bool:
        if self._min_fetch_interval_minutes <= 0:
            return False

        last_fetched = await self._store.last_fetched_at(source_key)
        if last_fetched is None:
            return False

        if last_fetched.tzinfo is None:
            last_fetched = last_fetched.replace(tzinfo=timezone.utc)

        age_seconds = (now - last_fetched).total_seconds()
        if age_seconds < self._min_fetch_interval_minutes * 60:
            log.info(
                "news_fetch_skipped",
                source=source_key,
                minutes_ago=round(age_seconds / 60, 1),
                min_interval_minutes=self._min_fetch_interval_minutes,
            )
            return True
        return False

    async def _score_new_articles(self, articles: list[Article]) -> None:
        from ze_news.credibility import score_article

        for article in articles:
            try:
                report = await score_article(
                    article,
                    client=self._client,
                    model=self._credibility_model,
                    llm_enabled=self._credibility_llm_enabled,
                )
                await self._store.update_credibility(article.url, report)
            except Exception as exc:
                log.warning("credibility_scoring_failed", url=article.url, error=str(exc))

    async def _emit_signals(
        self, articles: list[Article], *, bypass_gate: bool = False
    ) -> None:
        from ze_news.signals import ArticleSignalAdapter

        adapter = ArticleSignalAdapter()
        for article in articles:
            try:
                signal = adapter.to_signal(article)
                if bypass_gate or self._admission_gate is None:
                    await self._memory_store.ingest_signal(signal)
                else:
                    await self._admission_gate.check_and_ingest(signal)
            except Exception as exc:
                log.warning("news_signal_emit_failed", url=article.url, error=str(exc))
