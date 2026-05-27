"""Memory consolidator tests — ze wrapper over ze-core."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze.memory.consolidator import MemoryConsolidator
from ze_core.memory.consolidator import MemoryConsolidator as CoreMemoryConsolidator
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.memory.types import ConsolidationReport


def _store(**overrides):
    s = AsyncMock(spec=PostgresMemoryStore)
    s.fetch_active_facts = AsyncMock(return_value=[])
    s.mark_contradicted = AsyncMock()
    s.insert_merged_fact = AsyncMock()
    s.soft_expire_unreviewed_facts = AsyncMock(return_value=0)
    s.delete_expired_facts = AsyncMock(return_value=0)
    s.delete_contradicted_facts = AsyncMock(return_value=0)
    s.fetch_episode_candidates = AsyncMock(return_value=[])
    s.delete_old_episode_summaries = AsyncMock(return_value=0)
    s.insert_archive_episode = AsyncMock()
    s.delete_episodes_by_ids = AsyncMock()
    s.fetch_active_fact_summaries = AsyncMock(return_value=[])
    s.fetch_recent_episode_summaries = AsyncMock(return_value=[])
    s.upsert_profile = AsyncMock()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _embedder(vec=None):
    v = vec or [1.0, 0.0]
    e = MagicMock()
    e.encode = MagicMock(return_value=v)
    return e


def _client(response="{}"):
    c = AsyncMock()
    c.complete = AsyncMock(return_value=response)
    return c


def _consolidator(store=None, client=None, settings=None, embedder=None) -> MemoryConsolidator:
    store = store or _store()
    embedder = embedder or _embedder()
    client = client or _client()
    c = MemoryConsolidator(
        pool=MagicMock(),
        embedder=embedder,
        openrouter_client=client,
        settings=settings,
    )
    c._store = store
    c._inner = CoreMemoryConsolidator(
        store=store,
        embedder=embedder,
        openrouter_client=client,
        settings=settings,
    )
    return c


def _fact_row(key="k", value="v", confidence=1.0):
    return {"id": uuid4(), "key": key, "value": value, "agent": "global", "confidence": confidence}


class TestRun:
    async def test_returns_consolidation_report(self):
        report = await _consolidator().run()
        assert isinstance(report, ConsolidationReport)

    async def test_sets_telemetry_context(self):
        with patch("ze.memory.consolidator.set_flow_context") as flow, patch(
            "ze.memory.consolidator.set_agent_context"
        ) as agent:
            await _consolidator().run()
            flow.assert_called_once_with("memory_consolidation")
            agent.assert_called_once_with("memory_consolidation")


class TestDedupFacts:
    async def test_silent_merge_high_similarity(self):
        rows = [
            _fact_row("k1", "fact one", confidence=0.9),
            _fact_row("k2", "fact two", confidence=1.0),
        ]
        store = _store(fetch_active_facts=AsyncMock(return_value=rows))
        merged = await _consolidator(store=store, embedder=_embedder([1.0, 0.0])).dedup_facts()
        assert merged == 1


class TestSynthesiseProfile:
    async def test_delegates_to_update_profile(self):
        store = _store(
            fetch_active_fact_summaries=AsyncMock(return_value=[{"key": "name", "value": "Alice"}]),
            fetch_recent_episode_summaries=AsyncMock(return_value=[]),
        )
        profile_json = '{"preferences":"p","habits":"h","topics":"t","relationships":"r","goals":"g"}'
        result = await _consolidator(store=store, client=_client(response=profile_json)).synthesise_profile()
        assert result is True
        store.upsert_profile.assert_awaited_once()
