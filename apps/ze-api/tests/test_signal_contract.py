"""Tests for Phase 60 cross-plugin signal contract."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_agents.errors import AgentConfigError
from ze_memory.types import EntityRef, Signal
from ze_api.container import collect_plugin_signal_sources


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _make_signal(source: str, entity_names: list[str] = ()) -> Signal:
    return Signal(
        id=uuid.uuid4(),
        source=source,
        external_ref=f"{source}:ref:{uuid.uuid4()}",
        title=f"{source} signal",
        summary="test",
        occurred_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
        entities=[EntityRef(name=n, entity_type="org") for n in entity_names],
        magnitude=0.0,
    )


def _make_source(key: str):
    source = MagicMock()
    source.source_key = key
    return source


def _make_plugin(*source_keys: str):
    plugin = MagicMock()
    plugin.signal_sources.return_value = [_make_source(k) for k in source_keys]
    return plugin


# ── collect_plugin_signal_sources ─────────────────────────────────────────────

def test_no_sources_returns_empty_dict():
    plugins = [_make_plugin(), _make_plugin()]
    assert collect_plugin_signal_sources(plugins) == {}


def test_single_source_registered():
    plugins = [_make_plugin("news")]
    sources = collect_plugin_signal_sources(plugins)
    assert list(sources) == ["news"]


def test_multiple_plugins_multiple_sources():
    plugins = [_make_plugin("news"), _make_plugin("calendar")]
    sources = collect_plugin_signal_sources(plugins)
    assert set(sources) == {"news", "calendar"}


def test_duplicate_source_key_raises():
    plugins = [_make_plugin("news"), _make_plugin("news")]
    with pytest.raises(AgentConfigError, match="news"):
        collect_plugin_signal_sources(plugins)


def test_plugin_with_no_sources_contributes_none():
    """A plugin that returns [] from signal_sources() adds nothing."""
    no_source_plugin = _make_plugin()
    news_plugin = _make_plugin("news")
    sources = collect_plugin_signal_sources([no_source_plugin, news_plugin])
    assert set(sources) == {"news"}


def test_returned_sources_are_original_objects():
    news_source = _make_source("news")
    plugin = MagicMock()
    plugin.signal_sources.return_value = [news_source]
    sources = collect_plugin_signal_sources([plugin])
    assert sources["news"] is news_source


# ── SignalSource protocol ──────────────────────────────────────────────────────

def test_news_signal_source_satisfies_protocol():
    from ze_agents.signals import SignalSource
    from ze_news.signals import NewsSignalSource

    assert isinstance(NewsSignalSource(), SignalSource)


def test_calendar_signal_source_satisfies_protocol():
    from ze_agents.signals import SignalSource
    from ze_calendar.signals import CalendarSignalSource

    store = MagicMock()
    assert isinstance(CalendarSignalSource(store=store), SignalSource)


# ── multi-source admission (gate receives signals from multiple sources) ───────

@pytest.mark.asyncio
async def test_gate_receives_signals_from_multiple_sources():
    """Admission gate check_and_ingest is called for signals from both sources,
    with no engine changes required."""
    news_signal = _make_signal("news", ["Anthropic"])
    cal_signal = _make_signal("calendar", ["Anthropic"])

    gate = MagicMock()
    gate.check_and_ingest = AsyncMock(return_value="admit")

    # Simulate what each fetch job does: push → poll → gate
    from ze_news.signals import NewsSignalSource
    from ze_news.types import Article

    news_source = NewsSignalSource()
    article = Article(
        url="https://example.com/anthropic",
        source_key="tech",
        title="Anthropic signal",
        summary="test",
        published_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
        tags=["Anthropic"],
    )
    news_source.push([article])
    for sig in await news_source.poll(_EPOCH):
        await gate.check_and_ingest(sig)

    # Calendar source poll (direct)
    from ze_calendar.signals import CalendarSignalSource
    from ze_calendar.reminders.calendar_store import CalendarReminder

    reminder = CalendarReminder(
        id=uuid.uuid4(),
        event_id="evt-001",
        event_title="Anthropic board meeting",
        fire_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        label="meeting",
        sent=False,
        assessed_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
    )
    store = MagicMock()
    store.list_unsent = AsyncMock(return_value=[reminder])
    cal_source = CalendarSignalSource(store=store)
    for sig in await cal_source.poll(_EPOCH):
        await gate.check_and_ingest(sig)

    assert gate.check_and_ingest.call_count == 2
    sources_seen = {call.args[0].source for call in gate.check_and_ingest.call_args_list}
    assert sources_seen == {"news", "calendar"}


# ── cross-domain neighbourhood test ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_domain_signals_sharing_entity_both_reach_gate():
    """A news signal and a calendar signal about the same org both reach the
    admission gate — the engine sees signals from two independent sources that
    share an entity, enabling neighbourhood correlation."""
    shared_entity = "Anthropic"

    # Both signals reference the same org — the admission gate (watch buffer) can
    # elevate them jointly even if individually marginal.
    admitted: list[Signal] = []

    async def fake_ingest(signal: Signal):
        admitted.append(signal)

    gate = MagicMock()
    gate.check_and_ingest = AsyncMock(side_effect=fake_ingest)

    # News signal
    from ze_news.signals import NewsSignalSource
    from ze_news.types import Article

    ns = NewsSignalSource()
    ns.push([Article(
        url="https://example.com/news",
        source_key="tech",
        title=f"{shared_entity} raises funding",
        summary="test",
        published_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
        tags=[shared_entity],
    )])
    for sig in await ns.poll(_EPOCH):
        await gate.check_and_ingest(sig)

    # Calendar signal about the same org
    from ze_calendar.signals import CalendarSignalSource
    from ze_calendar.reminders.calendar_store import CalendarReminder

    store = MagicMock()
    store.list_unsent = AsyncMock(return_value=[CalendarReminder(
        id=uuid.uuid4(),
        event_id="evt-002",
        event_title=f"Meeting with {shared_entity} team",
        fire_at=datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc),
        label="meeting",
        sent=False,
        assessed_at=datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc),
    )])
    cs = CalendarSignalSource(store=store)
    for sig in await cs.poll(_EPOCH):
        await gate.check_and_ingest(sig)

    # Both signals reached the gate — cross-domain neighbourhood is possible
    assert len(admitted) == 2
    assert {s.source for s in admitted} == {"news", "calendar"}
