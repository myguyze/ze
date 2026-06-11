from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_personal.goals.postgres import PostgresGoalStore
from ze_personal.goals.types import PriorMilestoneOutput


def _make_row(
    *,
    milestone_id=None,
    goal_id=None,
    goal_title="Goal A",
    milestone_title="Step 1",
    output="Some output text",
    completed_days_ago=5,
):
    return {
        "milestone_id": milestone_id or uuid4(),
        "goal_id": goal_id or uuid4(),
        "goal_title": goal_title,
        "milestone_title": milestone_title,
        "output": output,
        "completed_days_ago": completed_days_ago,
    }


def make_conn(rows=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_store(conn=None):
    c = conn or make_conn()
    return PostgresGoalStore(pool=make_pool(c)), c


# ── list_completed_milestone_summaries ────────────────────────────────────────

async def test_returns_rows_within_window():
    row = _make_row(completed_days_ago=10)
    store, conn = make_store(make_conn([row]))

    results = await store.list_completed_milestone_summaries(days=90, limit=20)

    assert len(results) == 1
    assert results[0].goal_title == "Goal A"
    assert results[0].milestone_title == "Step 1"
    assert results[0].completed_days_ago == 10


async def test_returns_empty_when_no_rows():
    store, _ = make_store(make_conn([]))
    results = await store.list_completed_milestone_summaries()
    assert results == []


async def test_passes_exclude_goal_id_to_query():
    excluded = uuid4()
    store, conn = make_store(make_conn([]))

    await store.list_completed_milestone_summaries(exclude_goal_id=excluded)

    call_args = conn.fetch.call_args
    assert excluded in call_args.args


async def test_passes_none_exclude_goal_id_when_not_provided():
    store, conn = make_store(make_conn([]))

    await store.list_completed_milestone_summaries()

    call_args = conn.fetch.call_args
    assert None in call_args.args


async def test_respects_limit_parameter():
    store, conn = make_store(make_conn([]))

    await store.list_completed_milestone_summaries(limit=5)

    call_args = conn.fetch.call_args
    assert 5 in call_args.args


async def test_output_snippet_truncated_to_200_chars():
    long_output = "x" * 500
    row = _make_row(output=long_output)
    store, _ = make_store(make_conn([row]))

    results = await store.list_completed_milestone_summaries()

    assert len(results[0].output_snippet) == 200
    assert results[0].output_snippet == "x" * 200


async def test_returns_prior_milestone_output_dataclass():
    mid = uuid4()
    gid = uuid4()
    row = _make_row(milestone_id=mid, goal_id=gid)
    store, _ = make_store(make_conn([row]))

    results = await store.list_completed_milestone_summaries()

    r = results[0]
    assert isinstance(r, PriorMilestoneOutput)
    assert r.milestone_id == mid
    assert r.goal_id == gid


async def test_multiple_rows_returned_in_order():
    rows = [
        _make_row(milestone_title="Step 1", completed_days_ago=1),
        _make_row(milestone_title="Step 2", completed_days_ago=3),
    ]
    store, _ = make_store(make_conn(rows))

    results = await store.list_completed_milestone_summaries()

    assert len(results) == 2
    assert results[0].milestone_title == "Step 1"
    assert results[1].milestone_title == "Step 2"
