from __future__ import annotations

from ze_core.logging import get_logger
from ze_core.proactive.job import ProactiveJob, proactive_job
from ze_news.registry import SourceRegistry
from ze_news.store import NewsStore

log = get_logger(__name__)


@proactive_job
class NewsFetchJob:
    job_id = "news_fetch"

    def __init__(
        self,
        registry: SourceRegistry,
        store: NewsStore,
        retention_days: int = 7,
    ) -> None:
        self._registry = registry
        self._store = store
        self._retention_days = retention_days

    async def run(self) -> None:
        for source in self._registry.all():
            articles = await source.fetch(limit=50)
            if not articles:
                log.info("news_fetch_empty", source=source.key)
                continue
            new_count = await self._store.upsert(articles)
            log.info("news_fetch_done", source=source.key, fetched=len(articles), new=new_count)

        pruned = await self._store.prune(older_than_days=self._retention_days)
        if pruned:
            log.info("news_prune_done", pruned=pruned)
