from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_core.memory.consolidator import MemoryConsolidator
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.memory.types import ConsolidationReport


# ── helpers ───────────────────────────────────────────────────────────────────

def _store(**overrides):
    s = AsyncMock(spec=PostgresMemoryStore)
    s.fetch_active_facts = AsyncMock(return_value=[])
    s.mark_contradicted = AsyncMock()
    s.insert_merged_fact = AsyncMock()
    s.expire_unreviewed_facts = AsyncMock(return_value=0)
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


def _consolidator(store=None, client=None, settings=None, embedder=None):
    return MemoryConsolidator(
        store=store or _store(),
        embedder=embedder or _embedder(),
        openrouter_client=client or _client(),
        settings=settings,
    )


def _fact_row(key="k", value="v", confidence=1.0):
    return {"id": uuid4(), "key": key, "value": value, "agent": "global", "confidence": confidence}


# ── TestRun ───────────────────────────────────────────────────────────────────

class TestRun:
    async def test_returns_consolidation_report(self):
        report = await _consolidator().run()
        assert isinstance(report, ConsolidationReport)

    async def test_duration_ms_set(self):
        report = await _consolidator().run()
        assert report.duration_ms >= 0

    async def test_empty_store_all_zeros(self):
        report = await _consolidator().run()
        assert report.facts_merged == 0
        assert report.facts_soft_expired == 0
        assert report.facts_hard_deleted == 0
        assert report.episodes_archived == 0
        assert report.profile_updated is False


# ── TestDedupFacts ────────────────────────────────────────────────────────────

class TestDedupFacts:
    async def test_no_facts_returns_zero(self):
        assert await _consolidator().dedup_facts() == 0

    async def test_single_fact_returns_zero(self):
        store = _store(fetch_active_facts=AsyncMock(return_value=[_fact_row()]))
        assert await _consolidator(store=store).dedup_facts() == 0

    async def test_silent_merge_high_similarity(self):
        rows = [
            _fact_row("k1", "fact one", confidence=0.9),
            _fact_row("k2", "fact two", confidence=1.0),
        ]
        store = _store(fetch_active_facts=AsyncMock(return_value=rows))
        # identical vectors → cosine similarity = 1.0 ≥ 0.95 silent threshold
        merged = await _consolidator(store=store, embedder=_embedder([1.0, 0.0])).dedup_facts()
        assert merged == 1
        store.mark_contradicted.assert_awaited_once_with(rows[0]["id"])  # lower confidence

    async def test_llm_merge_medium_similarity(self):
        rows = [_fact_row("k1", "a"), _fact_row("k2", "b")]
        store = _store(fetch_active_facts=AsyncMock(return_value=rows))
        vecs = [[1.0, 0.0], [0.87, 0.49]]  # cos sim ≈ 0.87: above llm threshold, below silent
        idx = [0]
        def _encode(text):
            v = vecs[idx[0] % len(vecs)]
            idx[0] += 1
            return v
        embedder = MagicMock()
        embedder.encode = MagicMock(side_effect=_encode)
        client = _client(response="merged fact")
        merged = await _consolidator(store=store, embedder=embedder, client=client).dedup_facts()
        assert merged == 1
        client.complete.assert_awaited_once()
        assert store.insert_merged_fact.await_count == 1

    async def test_low_similarity_no_merge(self):
        rows = [_fact_row("k1", "a"), _fact_row("k2", "b")]
        store = _store(fetch_active_facts=AsyncMock(return_value=rows))
        vecs = [[1.0, 0.0], [0.0, 1.0]]  # orthogonal → sim = 0.0
        idx = [0]
        def _encode(text):
            v = vecs[idx[0] % len(vecs)]
            idx[0] += 1
            return v
        embedder = MagicMock()
        embedder.encode = MagicMock(side_effect=_encode)
        assert await _consolidator(store=store, embedder=embedder).dedup_facts() == 0


# ── TestExpireFacts ───────────────────────────────────────────────────────────

class TestExpireFacts:
    async def test_returns_counts_from_store(self):
        store = _store(
            expire_unreviewed_facts=AsyncMock(return_value=3),
            delete_contradicted_facts=AsyncMock(return_value=2),
        )
        soft, hard = await _consolidator(store=store).expire_facts()
        assert soft == 3
        assert hard == 2

    async def test_passes_ttl_from_settings(self):
        settings = {"memory": {"unreviewed_ttl_days": 45, "contradicted_ttl_days": 15}}
        store = _store(
            expire_unreviewed_facts=AsyncMock(return_value=0),
            delete_contradicted_facts=AsyncMock(return_value=0),
        )
        await _consolidator(store=store, settings=settings).expire_facts()
        store.expire_unreviewed_facts.assert_awaited_once_with(45)
        store.delete_contradicted_facts.assert_awaited_once_with(15)

    async def test_zero_counts_on_empty(self):
        soft, hard = await _consolidator().expire_facts()
        assert soft == 0
        assert hard == 0


# ── TestArchiveEpisodes ───────────────────────────────────────────────────────

class TestArchiveEpisodes:
    async def test_skips_llm_when_below_min_batch(self):
        client = _client()
        archived, _ = await _consolidator(client=client).archive_episodes()
        assert archived == 0
        client.complete.assert_not_awaited()

    async def test_archives_when_batch_full(self):
        candidates = [
            {"id": uuid4(), "prompt": f"p{i}", "response": f"r{i}", "summary": None}
            for i in range(10)
        ]
        store = _store(fetch_episode_candidates=AsyncMock(return_value=candidates))
        client = _client(response="archive summary")
        settings = {"memory": {"episode_recency_days": 14, "episode_min_archive_batch": 10, "episode_archive_batch": 20}}
        archived, _ = await _consolidator(store=store, client=client, settings=settings).archive_episodes()
        assert archived == 10
        client.complete.assert_awaited_once()
        store.insert_archive_episode.assert_awaited_once_with("archive summary")
        store.delete_episodes_by_ids.assert_awaited_once()

    async def test_llm_failure_returns_zero(self):
        candidates = [{"id": uuid4(), "prompt": "p", "response": "r", "summary": None} for _ in range(10)]
        store = _store(fetch_episode_candidates=AsyncMock(return_value=candidates))
        client = AsyncMock()
        client.complete = AsyncMock(side_effect=Exception("llm down"))
        settings = {"memory": {"episode_recency_days": 14, "episode_min_archive_batch": 10, "episode_archive_batch": 20}}
        archived, deleted = await _consolidator(store=store, client=client, settings=settings).archive_episodes()
        assert archived == 0
        assert deleted == 0


# ── TestUpdateProfile ─────────────────────────────────────────────────────────

class TestUpdateProfile:
    async def test_returns_false_when_no_data(self):
        assert await _consolidator().update_profile() is False

    async def test_upserts_valid_profile(self):
        store = _store(
            fetch_active_fact_summaries=AsyncMock(return_value=[{"key": "name", "value": "Alice"}]),
            fetch_recent_episode_summaries=AsyncMock(return_value=[{"summary": "discussed tech"}]),
        )
        profile_json = '{"preferences":"p","habits":"h","topics":"t","relationships":"r","goals":"g"}'
        client = _client(response=profile_json)
        result = await _consolidator(store=store, client=client).update_profile()
        assert result is True
        store.upsert_profile.assert_awaited_once_with("p", "h", "t", "r", "g")

    async def test_invalid_json_returns_false(self):
        store = _store(
            fetch_active_fact_summaries=AsyncMock(return_value=[{"key": "name", "value": "Alice"}]),
            fetch_recent_episode_summaries=AsyncMock(return_value=[]),
        )
        assert await _consolidator(store=store, client=_client(response="not json")).update_profile() is False

    async def test_missing_keys_returns_false(self):
        store = _store(
            fetch_active_fact_summaries=AsyncMock(return_value=[{"key": "name", "value": "Alice"}]),
            fetch_recent_episode_summaries=AsyncMock(return_value=[]),
        )
        assert await _consolidator(store=store, client=_client(response='{"preferences":"p"}')).update_profile() is False
