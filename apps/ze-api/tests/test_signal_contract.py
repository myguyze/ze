"""Tests for Phase 60 cross-plugin signal contract."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ze_agents.errors import AgentConfigError
from ze_api.container import collect_plugin_signal_sources


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


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
