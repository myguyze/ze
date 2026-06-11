from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_news.jobs.fetch import NewsFetchJob
from ze_news.registry import SourceRegistry
from ze_news.types import Article
from datetime import datetime, timezone


def _make_article(url="https://example.com/1") -> Article:
    return Article(
        url=url,
        source_key="test",
        title="Headline",
        summary="Summary.",
        published_at=datetime(2026, 6, 7, tzinfo=timezone.utc),
        tags=["global"],
    )


async def test_run_fetches_and_upserts():
    article = _make_article()
    source = MagicMock()
    source.key = "test_src"
    source.fetch = AsyncMock(return_value=[article])

    registry = SourceRegistry([source])

    store = MagicMock()
    store.upsert = AsyncMock(return_value=[article])
    store.prune = AsyncMock(return_value=0)

    job = NewsFetchJob(registry=registry, store=store, retention_days=7)
    await job.run()

    source.fetch.assert_called_once_with(limit=50)
    store.upsert.assert_called_once()
    store.prune.assert_called_once_with(older_than_days=7)


async def test_run_skips_empty_source():
    source = MagicMock()
    source.key = "empty_src"
    source.fetch = AsyncMock(return_value=[])

    registry = SourceRegistry([source])
    store = MagicMock()
    store.upsert = AsyncMock(return_value=[])
    store.prune = AsyncMock(return_value=0)

    job = NewsFetchJob(registry=registry, store=store)
    await job.run()

    store.upsert.assert_not_called()


async def test_run_continues_after_source_failure():
    failing = MagicMock()
    failing.key = "bad_src"
    failing.fetch = AsyncMock(return_value=[])

    article = _make_article()
    good = MagicMock()
    good.key = "good_src"
    good.fetch = AsyncMock(return_value=[article])

    registry = SourceRegistry([failing, good])
    store = MagicMock()
    store.upsert = AsyncMock(return_value=[article])
    store.prune = AsyncMock(return_value=0)

    job = NewsFetchJob(registry=registry, store=store)
    await job.run()

    store.upsert.assert_called_once()
