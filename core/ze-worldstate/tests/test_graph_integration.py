from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from ze_memory.graph.store import PostgresGraphStore
from ze_worldstate.store import PostgresLoopStore


class _FakeConn:
    """A minimal in-memory stand-in for the subset of asyncpg used by
    PostgresLoopStore.link_entity and PostgresGraphStore.list_relationships/expand,
    so US3's entity -> loop reachability (SC-004) can be exercised without a real DB.
    """

    def __init__(self) -> None:
        self.relationships: list[dict] = []

    async def execute(self, query: str, *args):
        if "INSERT INTO memory_relationships" in query and "has_open_loop" in query:
            entity_id, loop_id = args
            self.relationships.append(
                {
                    "id": uuid4(),
                    "source_id": entity_id,
                    "source_type": "entity",
                    "predicate": "has_open_loop",
                    "target_id": loop_id,
                    "target_type": "open_loop",
                    "target_text": None,
                    "confidence": 1.0,
                    "provenance_id": None,
                    "creation_method": "extracted",
                    "reviewed": False,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        return "INSERT 0 1"

    async def fetch(self, query: str, *args):
        if "FROM memory_relationships" in query:
            source_ids = args[0]
            return [r for r in self.relationships if r["source_id"] in source_ids]
        return []


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


async def test_loop_reachable_from_entity_neighbourhood():
    conn = _FakeConn()
    pool = _FakePool(conn)

    loop_store = PostgresLoopStore(pool=pool)
    graph_store = PostgresGraphStore(pool)

    entity_id = uuid4()
    loop_id = uuid4()

    await loop_store.link_entity(loop_id, entity_id)

    expansion = await graph_store.expand([entity_id])

    assert loop_id in expansion.open_loop_ids
