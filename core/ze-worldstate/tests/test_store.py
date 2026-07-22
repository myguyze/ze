from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ze_worldstate.errors import InvalidLoopTransitionError, LoopNotFoundError
from ze_worldstate.store import PostgresLoopStore
from ze_worldstate.types import LoopClaimKind, LoopProvenance, LoopState, OpenLoop
from tests.conftest import make_pool


def _row(**overrides) -> dict:
    base = {
        "id": uuid4(),
        "title": "Renew passport",
        "state": "suspected",
        "claim_kind": "suspicion",
        "provenance": "conversation",
        "confidence": 0.3,
        "goal_id": None,
        "dismissed_evidence_fingerprint": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "confirmed_at": None,
        "closed_at": None,
    }
    base.update(overrides)
    return base


async def test_create_returns_loop():
    row = _row()
    pool, conn = make_pool(fetchrow=row)
    store = PostgresLoopStore(pool=pool)

    loop = OpenLoop(
        title="Renew passport",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=0.3,
    )
    result = await store.create(loop)

    assert result.id == row["id"]
    assert result.state == LoopState.SUSPECTED
    conn.fetchrow.assert_awaited_once()


async def test_get_returns_none_when_missing():
    pool, conn = make_pool(fetchrow=None)
    store = PostgresLoopStore(pool=pool)
    assert await store.get(uuid4()) is None


async def test_list_filters_by_states():
    pool, conn = make_pool(fetch=[_row(), _row(state="active")])
    store = PostgresLoopStore(pool=pool)
    loops = await store.list(["suspected", "active"])
    assert len(loops) == 2
    conn.fetch.assert_awaited_once()


@pytest.mark.parametrize(
    "from_state,to_state",
    [
        ("suspected", "active"),
        ("suspected", "dropped"),
        ("active", "closed"),
        ("active", "dropped"),
        ("drifting", "closed"),
        ("drifting", "dropped"),
    ],
)
async def test_transition_allows_phase_a_matrix(from_state, to_state):
    loop_id = uuid4()
    get_row = _row(id=loop_id, state=from_state)
    updated_row = _row(id=loop_id, state=to_state)
    pool, conn = make_pool(fetchrow=get_row)
    store = PostgresLoopStore(pool=pool)

    # First fetchrow call is the internal `get`, second is the UPDATE ... RETURNING.
    conn.fetchrow = _sequenced_fetchrow([get_row, updated_row])

    result = await store.transition(loop_id, to_state)
    assert result.state == LoopState(to_state)


async def test_transition_rejects_active_to_drifting():
    loop_id = uuid4()
    get_row = _row(id=loop_id, state="active")
    pool, conn = make_pool(fetchrow=get_row)
    store = PostgresLoopStore(pool=pool)

    with pytest.raises(InvalidLoopTransitionError):
        await store.transition(loop_id, "drifting")


async def test_transition_raises_not_found():
    pool, conn = make_pool(fetchrow=None)
    store = PostgresLoopStore(pool=pool)
    with pytest.raises(LoopNotFoundError):
        await store.transition(uuid4(), "active")


def _sequenced_fetchrow(rows: list[dict]):
    from unittest.mock import AsyncMock

    it = iter(rows)

    async def _fn(*args, **kwargs):
        return next(it)

    return AsyncMock(side_effect=_fn)


async def test_link_entity_and_evidence_insert_relationship_rows():
    pool, conn = make_pool()
    store = PostgresLoopStore(pool=pool)

    await store.link_entity(uuid4(), uuid4())
    await store.link_evidence(uuid4(), "fact", uuid4())

    assert conn.execute.await_count == 2


async def test_count_evidence_links():
    pool, conn = make_pool(fetchrow={"n": 3})
    store = PostgresLoopStore(pool=pool)
    assert await store.count_evidence_links(uuid4()) == 3


async def test_list_evidence():
    pool, conn = make_pool(fetch=[{"target_type": "fact", "target_id": uuid4()}])
    store = PostgresLoopStore(pool=pool)
    refs = await store.list_evidence(uuid4())
    assert len(refs) == 1
    assert refs[0].evidence_type == "fact"
