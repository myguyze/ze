from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze.telegram.handlers.goals.stuck import handle_stuck
from ze_personal.goals.types import (
    GateStatus,
    Goal,
    GoalStatus,
    VerificationGate,
)
from tests.telegram.conftest import make_ctx, make_query


def _goal(status: GoalStatus = GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id=uuid4(),
        title="Learn Rust",
        objective="Build a CLI tool",
        success_condition="Tool works",
        status=status,
    )


def _gate(goal: Goal) -> VerificationGate:
    return VerificationGate(
        id=uuid4(),
        goal_id=goal.id,
        after_sequence=2,
        title="Mid-point review",
        status=GateStatus.PENDING,
    )


def _make_stuck_ctx(*, goal: Goal | None = None, gate: VerificationGate | None = None):
    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock()

    goal_store = AsyncMock()
    goal_store.get_goal = AsyncMock(return_value=goal)
    goal_store.get_pending_gate = AsyncMock(return_value=gate)
    goal_store.update_status = AsyncMock()

    executor = AsyncMock()
    executor.handle_gate_approved = AsyncMock(return_value=None)
    executor.handle_gate_stopped = AsyncMock(return_value=None)

    ctx = make_ctx(
        bot=bot_mock,
        goal_store=goal_store,
        goal_executor=executor,
    )
    return ctx, goal_store, executor


async def test_invalid_uuid_hex_answers_with_error():
    g = _goal()
    ctx, _, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:pause:not-a-uuid")
    await handle_stuck(ctx, query)
    query.answer.assert_called_once_with("Invalid goal reference.")


async def test_nonexistent_goal_answers_with_error():
    ctx, goal_store, _ = _make_stuck_ctx(goal=None)
    query = make_query(f"goal_stuck:pause:{uuid4().hex}")
    await handle_stuck(ctx, query)
    query.answer.assert_called_once_with("Goal not found.")


async def test_malformed_data_no_crash():
    ctx, _, _ = _make_stuck_ctx(goal=_goal())
    query = make_query("goal_stuck:only_two_parts")
    await handle_stuck(ctx, query)
    query.answer.assert_called_once()


async def test_pause_updates_status_and_removes_keyboard():
    g = _goal(GoalStatus.ACTIVE)
    ctx, goal_store, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:pause:{g.id.hex}")
    await handle_stuck(ctx, query)
    goal_store.update_status.assert_called_once_with(g.id, GoalStatus.PAUSED)
    query.message.edit_reply_markup.assert_called_once_with(reply_markup=None)
    query.message.answer.assert_called_once()


async def test_pause_noop_if_already_resolved():
    g = _goal(GoalStatus.COMPLETED)
    ctx, goal_store, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:pause:{g.id.hex}")
    await handle_stuck(ctx, query)
    goal_store.update_status.assert_not_called()
    query.message.edit_reply_markup.assert_not_called()


async def test_abandon_updates_status_and_removes_keyboard():
    g = _goal(GoalStatus.ACTIVE)
    ctx, goal_store, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:abandon:{g.id.hex}")
    await handle_stuck(ctx, query)
    goal_store.update_status.assert_called_once_with(g.id, GoalStatus.ABANDONED)
    query.message.edit_reply_markup.assert_called_once_with(reply_markup=None)


async def test_abandon_noop_if_already_abandoned():
    g = _goal(GoalStatus.ABANDONED)
    ctx, goal_store, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:abandon:{g.id.hex}")
    await handle_stuck(ctx, query)
    goal_store.update_status.assert_not_called()


async def test_redirect_removes_keyboard_and_sends_prompt():
    g = _goal()
    ctx, _, _ = _make_stuck_ctx(goal=g)
    query = make_query(f"goal_stuck:redirect:{g.id.hex}")
    await handle_stuck(ctx, query)
    query.message.edit_reply_markup.assert_called_once_with(reply_markup=None)
    query.message.answer.assert_called_once()
    assert "Learn Rust" in query.message.answer.call_args.args[0]


async def test_gate_approve_calls_handle_gate_approved_and_removes_keyboard():
    g = _goal(GoalStatus.AWAITING_GATE)
    gate = _gate(g)
    ctx, _, executor = _make_stuck_ctx(goal=g, gate=gate)
    query = make_query(f"goal_stuck:gate_approve:{g.id.hex}")
    await handle_stuck(ctx, query)
    await asyncio.sleep(0)
    executor.handle_gate_approved.assert_called_once_with(gate.id)
    query.message.edit_reply_markup.assert_called_once_with(reply_markup=None)
    query.message.answer.assert_called_once()


async def test_gate_approve_noop_if_no_pending_gate():
    g = _goal(GoalStatus.AWAITING_GATE)
    ctx, _, executor = _make_stuck_ctx(goal=g, gate=None)
    query = make_query(f"goal_stuck:gate_approve:{g.id.hex}")
    await handle_stuck(ctx, query)
    executor.handle_gate_approved.assert_not_called()


async def test_gate_stop_calls_handle_gate_stopped_and_removes_keyboard():
    g = _goal(GoalStatus.AWAITING_GATE)
    gate = _gate(g)
    ctx, _, executor = _make_stuck_ctx(goal=g, gate=gate)
    query = make_query(f"goal_stuck:gate_stop:{g.id.hex}")
    await handle_stuck(ctx, query)
    await asyncio.sleep(0)
    executor.handle_gate_stopped.assert_called_once_with(gate.id)
    query.message.edit_reply_markup.assert_called_once_with(reply_markup=None)


async def test_gate_stop_noop_if_no_pending_gate():
    g = _goal(GoalStatus.AWAITING_GATE)
    ctx, _, executor = _make_stuck_ctx(goal=g, gate=None)
    query = make_query(f"goal_stuck:gate_stop:{g.id.hex}")
    await handle_stuck(ctx, query)
    executor.handle_gate_stopped.assert_not_called()
