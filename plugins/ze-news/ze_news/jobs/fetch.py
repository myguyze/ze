from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ze_core.logging import get_logger
from ze_core.proactive.job import ProactiveJob, proactive_job
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
    ) -> None:
        self._registry = registry
        self._store = store
        self._retention_days = retention_days
        self._client = client
        self._credibility_enabled = credibility_enabled
        self._credibility_llm_enabled = credibility_llm_enabled
        self._credibility_model = credibility_model

    async def run(self) -> None:
        for source in self._registry.all():
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

        pruned = await self._store.prune(older_than_days=self._retention_days)
        if pruned:
            log.info("news_prune_done", pruned=pruned)

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
