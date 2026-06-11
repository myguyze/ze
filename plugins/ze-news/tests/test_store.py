from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_news.store import NewsStore
from ze_news.types import Article


def _make_article(**kwargs) -> Article:
    defaults = dict(
        url="https://example.com/article",
        source_key="test",
        title="Test Headline",
        summary="A short summary.",
        published_at=datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc),
        tags=["global"],
    )
    return Article(**{**defaults, **kwargs})


def _make_store():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    embedder = MagicMock()
    embedder.encode.return_value = [0.1] * 384

    return NewsStore(pool=pool, embedder=embedder), conn


async def test_upsert_new_article():
    store, conn = _make_store()
    conn.execute.return_value = "INSERT 0 1"

    article = _make_article()
    new_articles = await store.upsert([article])

    assert len(new_articles) == 1
    assert new_articles[0].url == article.url
    conn.execute.assert_called_once()


async def test_upsert_duplicate_skipped():
    store, conn = _make_store()
    conn.execute.return_value = "INSERT 0 0"

    new_articles = await store.upsert([_make_article()])
    assert new_articles == []


async def test_upsert_empty_list():
    store, conn = _make_store()
    new_articles = await store.upsert([])
    assert new_articles == []
    conn.execute.assert_not_called()


async def test_get_recent_no_tags():
    store, conn = _make_store()
    conn.fetch.return_value = []
    results = await store.get_recent(limit=5)
    assert results == []
    conn.fetch.assert_called_once()


async def test_get_recent_with_tags():
    store, conn = _make_store()
    conn.fetch.return_value = []
    await store.get_recent(limit=5, tags=["local"])
    args = conn.fetch.call_args[0]
    assert 5 in args
    assert ["local"] in args


async def test_prune_returns_count():
    store, conn = _make_store()
    conn.execute.return_value = "DELETE 3"
    count = await store.prune(older_than_days=7)
    assert count == 3
