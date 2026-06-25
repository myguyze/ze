from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.goal_actions import handle_action
from ze_automation.goals.types import Goal, GoalStatus, GateStatus, VerificationGate


def _make_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


def _make_container(*, store=None, executor=None, interface=None):
    container = MagicMock()
    container._plugin_stores = {
        "goal_store": store or AsyncMock(),
        "goal_executor": executor or AsyncMock(),
    }
    container.interface = interface or AsyncMock()
    container.interface.send_with_thread = AsyncMock()
    return container


@pytest.mark.asyncio
async def test_goal_plan_yes_approves_and_refreshes():
    goal_id = uuid4()
    goal = Goal(
        id=goal_id,
        title="Learn AI",
        objective="o",
        success_condition="s",
        status=GoalStatus.PLANNING,
    )
    store = AsyncMock()
    store.get_goal = AsyncMock(return_value=goal)
    executor = AsyncMock()
    executor.approve_plan = AsyncMock(return_value=True)
    conn_mgr = ConnectionManager()
    ws = _make_ws()
    await conn_mgr.connect(ws, AsyncMock())

    await handle_action(
        ws,
        {"payload": f"goal_plan:yes:{goal_id}"},
        _make_container(store=store, executor=executor),
        conn_mgr,
    )

    executor.approve_plan.assert_awaited_once_with(goal_id)
    frames = [call.args[0] for call in ws.send_json.call_args_list]
    assert any(f.get("type") == "refresh" and f.get("screen") == "goals" for f in frames)


@pytest.mark.asyncio
async def test_goal_approve_fires_gate_handler():
    gate_id = uuid4()
    goal_id = uuid4()
    gate = VerificationGate(
        id=gate_id,
        goal_id=goal_id,
        after_sequence=1,
        title="Checkpoint",
        status=GateStatus.AWAITING_APPROVAL,
    )
    goal = Goal(id=goal_id, title="Learn AI", objective="o", success_condition="s")
    store = AsyncMock()
    store.get_gate = AsyncMock(return_value=gate)
    store.get_goal = AsyncMock(return_value=goal)
    executor = AsyncMock()
    executor.handle_gate_approved = AsyncMock()
    conn_mgr = ConnectionManager()
    ws = _make_ws()
    await conn_mgr.connect(ws, AsyncMock())

    await handle_action(
        ws,
        {"payload": f"goal:approve:{gate_id}"},
        _make_container(store=store, executor=executor),
        conn_mgr,
    )

    executor.handle_gate_approved.assert_awaited_once_with(gate_id)


@pytest.mark.asyncio
async def test_goal_redirect_sets_pending_gate():
    gate_id = uuid4()
    goal_id = uuid4()
    gate = VerificationGate(
        id=gate_id,
        goal_id=goal_id,
        after_sequence=1,
        title="Checkpoint",
        status=GateStatus.AWAITING_APPROVAL,
    )
    goal = Goal(id=goal_id, title="Learn AI", objective="o", success_condition="s")
    store = AsyncMock()
    store.get_gate = AsyncMock(return_value=gate)
    store.get_goal = AsyncMock(return_value=goal)
    conn_mgr = ConnectionManager()
    ws = _make_ws()
    await conn_mgr.connect(ws, AsyncMock())

    await handle_action(
        ws,
        {"payload": f"goal:redirect:{gate_id}"},
        _make_container(store=store),
        conn_mgr,
    )

    assert conn_mgr.take_pending_gate_redirect() == gate_id


@pytest.mark.asyncio
async def test_goal_stuck_pause_updates_status():
    goal_id = uuid4()
    goal = Goal(
        id=goal_id,
        title="Learn AI",
        objective="o",
        success_condition="s",
        status=GoalStatus.ACTIVE,
    )
    store = AsyncMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.update_status = AsyncMock()
    conn_mgr = ConnectionManager()
    ws = _make_ws()
    await conn_mgr.connect(ws, AsyncMock())

    await handle_action(
        ws,
        {"payload": f"goal_stuck:pause:{goal_id.hex}"},
        _make_container(store=store),
        conn_mgr,
    )

    store.update_status.assert_awaited_once_with(goal_id, GoalStatus.PAUSED)
