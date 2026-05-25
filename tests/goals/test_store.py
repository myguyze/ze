from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.goals.store import GoalStore, _goal_from_row, _milestone_from_row, _gate_from_row
from ze.goals.types import Goal, GoalStatus, Milestone, MilestoneStatus, VerificationGate, GateStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    tx_cm = AsyncMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)
    return conn


def make_pool(conn=None):
    conn = conn or make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_store(conn=None):
    return GoalStore(pool=make_pool(conn))


_NOW = datetime.now(timezone.utc)


def make_goal_row(**overrides):
    defaults = {
        "id": uuid4(),
        "title": "Test Goal",
        "objective": "Do something",
        "success_condition": "It is done",
        "time_horizon": "2 weeks",
        "status": "active",
        "type": "custom",
        "learnings": "",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return defaults


def make_milestone_row(**overrides):
    defaults = {
        "id": uuid4(),
        "goal_id": uuid4(),
        "title": "Step 1",
        "description": "Do step 1",
        "sequence": 1,
        "agent_hint": "research",
        "intent": "execute",
        "status": "pending",
        "output": "",
        "completed_at": None,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return defaults


def make_gate_row(**overrides):
    defaults = {
        "id": uuid4(),
        "goal_id": uuid4(),
        "after_sequence": 1,
        "title": "Review progress",
        "status": "pending",
        "context_summary": "",
        "plan_summary": "",
        "user_feedback": "",
        "fired_at": None,
        "resolved_at": None,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return defaults


# ── Row mappers ───────────────────────────────────────────────────────────────

def test_goal_from_row_maps_fields():
    row = make_goal_row(status="active", title="My Goal")
    goal = _goal_from_row(row)
    assert goal.title == "My Goal"
    assert goal.status == GoalStatus.ACTIVE


def test_milestone_from_row_maps_fields():
    row = make_milestone_row(status="completed", sequence=3)
    m = _milestone_from_row(row)
    assert m.sequence == 3
    assert m.status == MilestoneStatus.COMPLETED


def test_gate_from_row_maps_fields():
    row = make_gate_row(status="awaiting_approval", after_sequence=2)
    gate = _gate_from_row(row)
    assert gate.after_sequence == 2
    assert gate.status == GateStatus.AWAITING_APPROVAL


# ── create_goal ───────────────────────────────────────────────────────────────

async def test_create_goal_returns_goal_with_id():
    row = make_goal_row()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(conn)

    goal = Goal(
        title="Test",
        objective="obj",
        success_condition="done",
        time_horizon="1 week",
    )
    result = await store.create_goal(goal)
    assert result.id == row["id"]
    assert result.title == row["title"]


# ── list_active ───────────────────────────────────────────────────────────────

async def test_list_active_returns_empty_when_none():
    store = make_store()
    result = await store.list_active()
    assert result == []


async def test_list_active_returns_active_goals():
    rows = [make_goal_row(status="active"), make_goal_row(status="awaiting_gate")]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)
    store = make_store(conn)
    goals = await store.list_active()
    assert len(goals) == 2


# ── update_status ─────────────────────────────────────────────────────────────

async def test_update_status_calls_execute():
    conn = make_conn()
    store = make_store(conn)
    goal_id = uuid4()
    await store.update_status(goal_id, GoalStatus.PAUSED)
    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args
    assert "UPDATE goals" in call_args.args[0]
    assert call_args.args[1] == "paused"


# ── fire_gate / resolve_gate ──────────────────────────────────────────────────

async def test_fire_gate_updates_status_and_summaries():
    conn = make_conn()
    store = make_store(conn)
    gate_id = uuid4()
    await store.fire_gate(gate_id, "ctx", "plan")
    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args.args[0]
    assert "awaiting_approval" in sql
    assert conn.execute.call_args.args[1] == "ctx"
    assert conn.execute.call_args.args[2] == "plan"


async def test_resolve_gate_stores_feedback():
    conn = make_conn()
    store = make_store(conn)
    gate_id = uuid4()
    await store.resolve_gate(gate_id, GateStatus.REDIRECTED, user_feedback="new dir")
    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args
    assert call_args.args[1] == "redirected"
    assert call_args.args[2] == "new dir"


async def test_replace_pending_gates_deletes_and_inserts():
    conn = make_conn()
    new_row = make_gate_row(after_sequence=4, title="New gate")
    conn.fetchrow = AsyncMock(return_value=new_row)
    store = make_store(conn)
    goal_id = uuid4()
    gate = VerificationGate(goal_id=goal_id, after_sequence=4, title="New gate")
    results = await store.replace_pending_gates(goal_id, [gate])
    assert len(results) == 1
    sql = conn.execute.call_args.args[0]
    assert "DELETE FROM goal_gates" in sql
    assert "pending" in sql


# ── get_pending_gate ──────────────────────────────────────────────────────────

async def test_get_pending_gate_returns_none_when_no_gate():
    store = make_store()
    result = await store.get_pending_gate(uuid4())
    assert result is None


async def test_get_pending_gate_returns_gate():
    row = make_gate_row(status="pending")
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(conn)
    gate = await store.get_pending_gate(uuid4())
    assert gate is not None
    assert gate.status == GateStatus.PENDING
