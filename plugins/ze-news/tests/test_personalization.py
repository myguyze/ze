from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_news.store import NewsStore
from ze_news.types import Article, PersonalizationContext


def _make_article(**kwargs) -> Article:
    defaults = dict(
        url="https://example.com/article",
        source_key="test",
        title="Test Headline",
        summary="A short summary about technology.",
        published_at=datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc),
        tags=["global"],
    )
    return Article(**{**defaults, **kwargs})


def _make_store(encode_return=None):
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    embedder = MagicMock()
    embedder.encode.return_value = encode_return or [0.1] * 384

    return NewsStore(pool=pool, embedder=embedder), conn


# ── PersonalizationContext ──────────────────────────────────────────────────

def test_personalization_context_defaults():
    ctx = PersonalizationContext(interest_text="tech AI")
    assert ctx.explore_ratio == 0.2
    assert ctx.exclusions == []
    assert ctx.fact_count == 0


def test_personalization_context_custom():
    ctx = PersonalizationContext(
        interest_text="sports football",
        exclusions=["football"],
        explore_ratio=0.3,
        fact_count=10,
    )
    assert ctx.exclusions == ["football"]
    assert ctx.explore_ratio == 0.3
    assert ctx.fact_count == 10


# ── _apply_exclusions ────────────────────────────────────────────────────────

def test_apply_exclusions_filters_by_title():
    store, _ = _make_store()
    articles = [
        _make_article(title="Football match results"),
        _make_article(title="Tech startup raises funding", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1
    assert result[0].title == "Tech startup raises funding"


def test_apply_exclusions_filters_by_summary():
    store, _ = _make_store()
    articles = [
        _make_article(summary="The match was about football tactics"),
        _make_article(summary="AI breakthroughs in 2026", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1
    assert "AI" in result[0].summary


def test_apply_exclusions_word_boundary():
    store, _ = _make_store()
    articles = [
        _make_article(title="New transport routes announced"),
        _make_article(title="Sport highlights of the week", url="https://example.com/2"),
    ]
    # "sport" should NOT match "transport" due to word boundary, but SHOULD match "Sport highlights"
    result = store._apply_exclusions(articles, ["sport"])
    assert len(result) == 1
    assert "transport" in result[0].title


def test_apply_exclusions_empty_returns_all():
    store, _ = _make_store()
    articles = [_make_article(), _make_article(url="https://example.com/2")]
    result = store._apply_exclusions(articles, [])
    assert len(result) == 2


def test_apply_exclusions_case_insensitive():
    store, _ = _make_store()
    articles = [
        _make_article(title="FOOTBALL news today"),
        _make_article(title="Tech news", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1


# ── get_personalized fallback ────────────────────────────────────────────────

async def test_get_personalized_falls_back_when_empty_interest():
    store, conn = _make_store()
    conn.fetch.return_value = []

    ctx = PersonalizationContext(interest_text="", fact_count=10)
    relevant, discovery = await store.get_personalized(ctx, limit=5)

    assert discovery == []
    conn.fetch.assert_called_once()  # called get_recent


async def test_get_personalized_falls_back_below_min_facts():
    store, conn = _make_store()
    conn.fetch.return_value = []

    ctx = PersonalizationContext(interest_text="tech AI", fact_count=2)
    relevant, discovery = await store.get_personalized(ctx, limit=5, min_facts=5)

    assert discovery == []
    conn.fetch.assert_called_once()  # get_recent called


# ── get_personalized scoring ─────────────────────────────────────────────────

async def test_get_personalized_splits_into_buckets():
    store, conn = _make_store()

    articles = [
        _make_article(
            url=f"https://example.com/{i}",
            title=f"Article {i}",
            published_at=datetime(2026, 6, 7, 12, i, tzinfo=timezone.utc),
        )
        for i in range(10)
    ]

    def _make_row(a):
        row = MagicMock()
        row.__getitem__ = lambda self, k: getattr(a, k) if k != "tags" else a.tags
        return row

    conn.fetch.return_value = [_make_row(a) for a in articles]

    ctx = PersonalizationContext(interest_text="technology AI", fact_count=10)
    relevant, discovery = await store.get_personalized(ctx, limit=5, min_facts=5)

    assert len(relevant) + len(discovery) <= 5
    assert len(relevant) > 0


async def test_get_personalized_discovery_sorted_by_recency():
    import math
    store, conn = _make_store()

    t1 = datetime(2026, 6, 7, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 7, 11, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)

    articles = [
        _make_article(url="https://example.com/1", title="A1", published_at=t1),
        _make_article(url="https://example.com/2", title="A2", published_at=t2),
        _make_article(url="https://example.com/3", title="A3", published_at=t3),
        _make_article(url="https://example.com/4", title="A4", published_at=t1),
        _make_article(url="https://example.com/5", title="A5", published_at=t2),
        _make_article(url="https://example.com/6", title="A6", published_at=t3),
    ]

    def _make_row(a):
        row = MagicMock()
        row.__getitem__ = lambda self, k: getattr(a, k, []) if k != "tags" else a.tags
        return row

    conn.fetch.return_value = [_make_row(a) for a in articles]

    ctx = PersonalizationContext(interest_text="AI tech", fact_count=10, explore_ratio=0.5)
    relevant, discovery = await store.get_personalized(ctx, limit=4, min_facts=5)

    if discovery:
        times = [a.published_at for a in discovery]
        assert times == sorted(times, reverse=True)


# ── _score_articles ───────────────────────────────────────────────────────────

def test_score_articles_zero_vector_gives_zero():
    store, _ = _make_store()
    article = _make_article()
    store._embedder.encode.return_value = [0.0] * 384
    results = store._score_articles([article], [0.0] * 384)
    assert results[0][1] == 0.0


def test_score_articles_identical_vectors_give_one():
    import numpy as np
    store, _ = _make_store()
    vec = [0.1] * 384
    store._embedder.encode.return_value = vec
    article = _make_article()
    results = store._score_articles([article], vec)
    assert abs(results[0][1] - 1.0) < 1e-6
