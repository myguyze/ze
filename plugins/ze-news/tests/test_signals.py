"""Tests for ArticleSignalAdapter (Phase 55 news emitter)."""
from __future__ import annotations

from datetime import datetime, timezone

from ze_memory.types import EntityRef

from ze_news.signals import ArticleSignalAdapter
from ze_news.types import Article


def _make_article(**kwargs) -> Article:
    defaults = dict(
        url="https://bbc.co.uk/news/technology/123",
        source_key="bbc_tech",
        title="Anthropic releases Claude 4",
        summary="Anthropic has released a new AI model called Claude 4.",
        published_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
        tags=["tech", "ai"],
    )
    defaults.update(kwargs)
    return Article(**defaults)


# ── round-trip ────────────────────────────────────────────────────────────────

def test_external_ref_equals_article_url():
    adapter = ArticleSignalAdapter()
    article = _make_article()
    signal = adapter.to_signal(article)
    assert signal.external_ref == article.url


def test_source_is_news():
    adapter = ArticleSignalAdapter()
    signal = adapter.to_signal(_make_article())
    assert signal.source == "news"


def test_title_and_summary_preserved():
    adapter = ArticleSignalAdapter()
    article = _make_article()
    signal = adapter.to_signal(article)
    assert signal.title == article.title
    assert signal.summary == article.summary


def test_occurred_at_matches_published_at():
    adapter = ArticleSignalAdapter()
    article = _make_article()
    signal = adapter.to_signal(article)
    assert signal.occurred_at == article.published_at


def test_expires_at_is_none_on_ingest():
    adapter = ArticleSignalAdapter()
    signal = adapter.to_signal(_make_article())
    assert signal.expires_at is None


# ── entity refs from tags ─────────────────────────────────────────────────────

def test_tags_become_topic_entity_refs():
    adapter = ArticleSignalAdapter()
    article = _make_article(tags=["tech", "ai", "anthropic"])
    signal = adapter.to_signal(article)

    assert len(signal.entities) == 3
    assert all(e.entity_type == "topic" for e in signal.entities)
    names = [e.name for e in signal.entities]
    assert "tech" in names
    assert "ai" in names
    assert "anthropic" in names


def test_empty_tags_produces_no_entities():
    adapter = ArticleSignalAdapter()
    signal = adapter.to_signal(_make_article(tags=[]))
    assert signal.entities == []


def test_short_tags_are_filtered():
    adapter = ArticleSignalAdapter()
    # single-char tag should be dropped
    signal = adapter.to_signal(_make_article(tags=["a", "tech"]))
    names = [e.name for e in signal.entities]
    assert "a" not in names
    assert "tech" in names


def test_each_call_produces_unique_signal_id():
    adapter = ArticleSignalAdapter()
    article = _make_article()
    s1 = adapter.to_signal(article)
    s2 = adapter.to_signal(article)
    assert s1.id != s2.id


def test_entity_refs_are_entity_ref_instances():
    adapter = ArticleSignalAdapter()
    signal = adapter.to_signal(_make_article(tags=["fintech"]))
    assert all(isinstance(e, EntityRef) for e in signal.entities)
