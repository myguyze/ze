"""Tests for PostgresMemoryStore write paths: propose_events, propose_procedure, upsert_entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
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
