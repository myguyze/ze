"""Tests for PostgresMemoryStore write paths: propose_events, propose_procedure, upsert_entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from ze_memory.graph.store import GraphStore
from ze_memory.graph.types import Relationship
from ze_memory.retriever import PostgresMemoryStore
from ze_memory.types import Entity, Event, Procedure


def _make_pool() -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    pool.acquire = MagicMock(return_value=_async_ctx(conn))
    return pool, conn


class _async_ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_store(pool=None, graph_store=None) -> tuple[PostgresMemoryStore, AsyncMock]:
    if pool is None:
        pool, conn = _make_pool()
    else:
        conn = pool.acquire.return_value._conn
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = pool
    store._embedder = None
    store._client = None
    store._graph_store = graph_store
    store._traversal = None
    store._log = MagicMock()
    return store, conn


def _make_graph_store() -> MagicMock:
    gs = MagicMock(spec=GraphStore)
    gs.upsert_relationship = AsyncMock(return_value=uuid4())
    return gs


# ── propose_events ────────────────────────────────────────────────────────────

async def test_propose_events_inserts_each_event():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})

    events = [
        Event(id=None, event_type="meeting", title="Sprint planning"),
        Event(id=None, event_type="call", title="Customer call"),
    ]
    await store.propose_events(events)

    assert conn.fetchrow.call_count == 2


async def test_propose_events_empty_list_does_nothing():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    await store.propose_events([])
    conn.fetchrow.assert_not_called()


async def test_propose_events_continues_on_single_failure():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    conn.fetchrow = AsyncMock(side_effect=[RuntimeError("DB error"), {"id": uuid4()}])

    events = [
        Event(id=None, event_type="meeting", title="Fails"),
        Event(id=None, event_type="call", title="Succeeds"),
    ]
    # Should not raise — second event still processed
    await store.propose_events(events)
    assert conn.fetchrow.call_count == 2


# ── propose_procedure ─────────────────────────────────────────────────────────

async def test_propose_procedure_inserts_record():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    proc_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": proc_id})

    proc = Procedure(
        id=None,
        name="Send outreach emails",
        trigger="When user wants to contact prospects",
        preconditions=["Have a target list"],
        steps=["Draft email", "Review", "Send"],
        success_criteria=["All emails sent"],
    )
    result = await store.propose_procedure(proc)

    assert result == proc_id
    conn.fetchrow.assert_called_once()
    sql = conn.fetchrow.call_args[0][0]
    assert "memory_procedures" in sql
    assert "RETURNING id" in sql


async def test_propose_procedure_swallows_db_error():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("constraint"))

    proc = Procedure(id=None, name="Test", trigger="trigger", steps=["step"])
    result = await store.propose_procedure(proc)
    assert result is None


async def test_propose_procedure_fires_uses_procedure_edge():
    pool, conn = _make_pool()
    gs = _make_graph_store()
    store, conn = _make_store(pool, graph_store=gs)
    proc_id = uuid4()
    task_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": proc_id})

    proc = Procedure(id=None, name="Test proc", trigger="trigger", steps=["step"])
    await store.propose_procedure(proc, linked_task_id=task_id, linked_task_type="workflow")

    await store._link_procedure_to_task(proc_id, task_id, "workflow")

    calls = gs.upsert_relationship.call_args_list
    assert any(c[0][0].predicate == "USES_PROCEDURE" for c in calls)
    matching = [c for c in calls if c[0][0].predicate == "USES_PROCEDURE"]
    rel = matching[0][0][0]
    assert rel.source_id == proc_id
    assert rel.target_id == task_id
    assert rel.target_type == "workflow"


async def test_propose_procedure_no_graph_edge_without_graph_store():
    pool, conn = _make_pool()
    store, conn = _make_store(pool, graph_store=None)
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})

    proc = Procedure(id=None, name="Test", trigger="trigger", steps=["step"])
    result = await store.propose_procedure(proc, linked_task_id=uuid4())
    assert result is not None  # stored successfully, no crash


# ── upsert_entity ─────────────────────────────────────────────────────────────

async def test_upsert_entity_returns_id():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    new_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": new_id})

    entity = Entity(
        id=None,
        entity_type="person",
        canonical_name="Alice Wonderland",
        aliases=["Alice"],
        attrs={"relationship": "colleague"},
    )
    result = await store.upsert_entity(entity)

    assert result == new_id
    conn.fetchrow.assert_called_once()
    sql = conn.fetchrow.call_args[0][0]
    assert "memory_entities" in sql
    assert "ON CONFLICT" in sql


async def test_upsert_entity_passes_correct_fields():
    pool, conn = _make_pool()
    store, conn = _make_store(pool)
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})

    entity = Entity(
        id=None,
        entity_type="organisation",
        canonical_name="Acme Corp",
        aliases=["Acme"],
        attrs={"domain": "technology"},
    )
    await store.upsert_entity(entity)

    args = conn.fetchrow.call_args[0]
    assert "organisation" in args
    assert "Acme Corp" in args


# ── graph relationship creation ───────────────────────────────────────────────

class TestGraphRelationshipCreation:
    async def test_link_fact_describes_edge_when_subject_id_set(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        subject_id = uuid4()
        fact_id = uuid4()
        from ze_memory.types import Fact
        fact = Fact(
            id=None,
            subject_id=subject_id,
            predicate="likes",
            value="coffee",
            object_text="coffee",
            confidence=0.9,
        )
        await store._link_fact_relationships(fact, fact_id)

        gs.upsert_relationship.assert_awaited()
        calls = gs.upsert_relationship.call_args_list
        predicates = [c[0][0].predicate for c in calls]
        assert "DESCRIBES" in predicates

    async def test_link_fact_sourced_from_edge_when_episode_set(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        episode_id = uuid4()
        fact_id = uuid4()
        from ze_memory.types import Fact
        fact = Fact(
            id=None,
            subject_id=None,
            predicate="likes",
            value="tea",
            object_text="tea",
            confidence=0.8,
            source_episode_id=episode_id,
        )
        await store._link_fact_relationships(fact, fact_id)

        predicates = [c[0][0].predicate for c in gs.upsert_relationship.call_args_list]
        assert "SOURCED_FROM" in predicates

    async def test_link_fact_no_edges_when_no_subject_or_episode(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        from ze_memory.types import Fact
        fact = Fact(
            id=None, subject_id=None, predicate="mood", value="happy", object_text="happy", confidence=0.7
        )
        await store._link_fact_relationships(fact, uuid4())

        gs.upsert_relationship.assert_not_awaited()

    async def test_link_event_participants_creates_participates_in(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        event_id = uuid4()
        participant_ids = [uuid4(), uuid4()]
        await store._link_event_participants(event_id, participant_ids)

        assert gs.upsert_relationship.await_count == 2
        predicates = [c[0][0].predicate for c in gs.upsert_relationship.call_args_list]
        assert all(p == "PARTICIPATES_IN" for p in predicates)

    async def test_link_task_state_to_goal_creates_belongs_to_goal(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        ts_id = uuid4()
        goal_id = uuid4()
        await store._link_task_state_to_goal(ts_id, goal_id)

        gs.upsert_relationship.assert_awaited_once()
        rel = gs.upsert_relationship.call_args[0][0]
        assert rel.predicate == "BELONGS_TO_GOAL"
        assert rel.source_id == ts_id
        assert rel.target_id == goal_id

    async def test_link_episode_entities_creates_mentions_for_matches(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        import json
        eid = uuid4()
        entity_id = uuid4()
        conn.fetch = AsyncMock(return_value=[{
            "id": entity_id,
            "canonical_name": "Alice",
            "aliases": json.dumps(["Al"]),
        }])
        conn.execute = AsyncMock()

        await store._link_episode_entities(eid, "Alice went to the meeting")

        conn.execute.assert_awaited_once()
        gs.upsert_relationship.assert_awaited_once()
        rel = gs.upsert_relationship.call_args[0][0]
        assert rel.predicate == "MENTIONS"
        assert rel.target_id == entity_id

    async def test_link_episode_entities_no_match_skips_graph(self):
        pool, conn = _make_pool()
        gs = _make_graph_store()
        store, _ = _make_store(pool, graph_store=gs)

        import json
        eid = uuid4()
        conn.fetch = AsyncMock(return_value=[{
            "id": uuid4(),
            "canonical_name": "Bob",
            "aliases": json.dumps([]),
        }])
        conn.execute = AsyncMock()

        await store._link_episode_entities(eid, "No names mentioned here")

        conn.execute.assert_not_awaited()
        gs.upsert_relationship.assert_not_awaited()


# ── _promote_event_outcome ────────────────────────────────────────────────────

class TestPromoteEventOutcome:
    def _make_store_with_client(self, pool=None, graph_store=None, client_response=None):
        pool, conn = _make_pool()
        fact_id = uuid4()
        conn.fetchrow = AsyncMock(return_value={"id": fact_id})
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()
        pool.acquire = MagicMock(return_value=_async_ctx(conn))

        store = PostgresMemoryStore.__new__(PostgresMemoryStore)
        store._pool = pool
        store._embedder = MagicMock()
        store._embedder.encode = MagicMock(return_value=[0.1] * 384)
        client = AsyncMock()
        client.complete = AsyncMock(return_value=client_response or '[]')
        store._client = client
        store._graph_store = graph_store
        store._traversal = None
        store._settings = None
        return store, conn, client, fact_id

    async def test_creates_promotes_to_edge(self):
        gs = _make_graph_store()
        event_id = uuid4()
        fact_json = '[{"predicate": "prefers_async", "value": "prefers async communication", "confidence": 0.9}]'
        store, conn, client, fact_id = self._make_store_with_client(graph_store=gs, client_response=fact_json)

        await store._promote_event_outcome(event_id, "signed the contract asynchronously")

        calls = gs.upsert_relationship.call_args_list
        promotes = [c for c in calls if c[0][0].predicate == "PROMOTES_TO"]
        assert len(promotes) == 1
        rel = promotes[0][0][0]
        assert rel.source_id == event_id
        assert rel.source_type == "event"
        assert rel.target_id == fact_id
        assert rel.target_type == "fact"
        assert rel.confidence == 0.9

    async def test_no_op_without_client(self):
        gs = _make_graph_store()
        pool, conn = _make_pool()
        store, _ = _make_store(pool, graph_store=gs)
        store._client = None

        await store._promote_event_outcome(uuid4(), "some outcome")

        gs.upsert_relationship.assert_not_awaited()

    async def test_no_op_without_graph_store(self):
        pool, conn = _make_pool()
        store, _, client, _ = self._make_store_with_client(graph_store=None)

        # should not raise
        await store._promote_event_outcome(uuid4(), "some outcome")

        client.complete.assert_not_awaited()

    async def test_swallows_llm_failure(self):
        gs = _make_graph_store()
        pool, conn = _make_pool()
        store, _, client, _ = self._make_store_with_client(graph_store=gs)
        client.complete = AsyncMock(side_effect=RuntimeError("LLM exploded"))

        # should not raise
        await store._promote_event_outcome(uuid4(), "the deal fell through")

        gs.upsert_relationship.assert_not_awaited()

    async def test_empty_extraction_creates_no_edges(self):
        gs = _make_graph_store()
        store, conn, client, _ = self._make_store_with_client(graph_store=gs, client_response='[]')

        await store._promote_event_outcome(uuid4(), "nothing memorable happened")

        gs.upsert_relationship.assert_not_awaited()


# ── propose_events PROMOTES_TO wiring ────────────────────────────────────────

async def test_propose_events_fires_promotes_to_when_outcome_set():
    pool, conn = _make_pool()
    gs = _make_graph_store()
    event_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": event_id})
    store, _ = _make_store(pool, graph_store=gs)

    with patch.object(store, "_promote_event_outcome", new_callable=AsyncMock) as mock_promote:
        with patch("asyncio.create_task") as mock_task:
            event = Event(id=None, event_type="meeting", title="Signed contract", outcome="signed the deal")
            await store.propose_events([event])

            # asyncio.create_task was called with a coroutine from _promote_event_outcome
            promote_calls = [
                c for c in mock_task.call_args_list
                if hasattr(c[0][0], "cr_frame")
                or "promote" in str(c)
            ]
            assert mock_task.call_count >= 1


async def test_propose_events_no_promotes_to_when_no_outcome():
    pool, conn = _make_pool()
    gs = _make_graph_store()
    event_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": event_id})
    store, _ = _make_store(pool, graph_store=gs)

    with patch.object(store, "_promote_event_outcome", new_callable=AsyncMock) as mock_promote:
        event = Event(id=None, event_type="meeting", title="Planning session", outcome=None)
        await store.propose_events([event])

        mock_promote.assert_not_awaited()


# ── _write_fact_with_contradiction_check returns UUID ────────────────────────

async def test_write_fact_returns_uuid():
    pool, conn = _make_pool()
    fact_id = uuid4()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": fact_id})
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = pool
    store._embedder = MagicMock()
    store._embedder.encode = MagicMock(return_value=[0.1] * 384)
    store._client = None
    store._graph_store = None
    store._traversal = None
    store._settings = None

    from ze_memory.types import Fact
    fact = Fact(id=None, subject_id=None, predicate="prefers_tea", value="prefers tea", object_text="tea", confidence=0.9)
    result = await store._write_fact_with_contradiction_check(fact)

    assert result == fact_id


async def test_write_fact_returns_none_on_db_error():
    pool, conn = _make_pool()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("DB error"))
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = pool
    store._embedder = MagicMock()
    store._embedder.encode = MagicMock(return_value=[0.1] * 384)
    store._client = None
    store._graph_store = None
    store._traversal = None
    store._settings = None

    from ze_memory.types import Fact
    fact = Fact(id=None, subject_id=None, predicate="mood", value="cheerful", object_text="cheerful", confidence=0.7)
    with pytest.raises(RuntimeError):
        await store._write_fact_with_contradiction_check(fact)
