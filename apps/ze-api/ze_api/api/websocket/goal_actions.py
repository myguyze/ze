from __future__ import annotations

import html
import re
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from ze_agents.interface.types import OutboundMessage
from ze_api.api.websocket.connection import ConnectionManager
from ze_automation.goals.types import GoalStatus
from ze_logging import get_logger

log = get_logger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


async def handle_action(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
) -> None:
    payload = str(data.get("payload") or "").strip()
    thread_id: str | None = data.get("thread_id") or None
    if not payload:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "payload required"}, thread_id
        )
        return

    store = container._plugin_stores.get("goal_store")
    executor = container._plugin_stores.get("goal_executor")
    if store is None or executor is None:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Goal engine unavailable"}, thread_id
        )
        return

    parts = payload.split(":", 2)
    if len(parts) != 3:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Unrecognised action."}, thread_id
        )
        return

    prefix, action, id_str = parts

    try:
        if prefix == "goal_plan":
            await _handle_plan_action(
                container, conn_mgr, executor, store, action, id_str, thread_id
            )
        elif prefix == "goal":
            await _handle_gate_action(
                container, conn_mgr, executor, store, action, id_str, thread_id
            )
        elif prefix == "goal_stuck":
            await _handle_stuck_action(
                container, conn_mgr, executor, store, action, id_str, thread_id
            )
        else:
            await conn_mgr.send_frame(
                {"type": "error", "detail": "Unrecognised action."}, thread_id
            )
    except ValueError:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Invalid reference."}, thread_id
        )
    except Exception as exc:
        log.exception("ws_goal_action_failed", payload=payload, error=str(exc))
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Action failed."}, thread_id
        )


async def _handle_plan_action(
    container: Any,
    conn_mgr: ConnectionManager,
    executor: Any,
    store: Any,
    action: str,
    goal_id_str: str,
    thread_id: str | None,
) -> None:
    goal_id = UUID(goal_id_str)
    goal = await store.get_goal(goal_id)
    if goal is None:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Goal not found."}, thread_id
        )
        return

    title = html.escape(goal.title)
    if action == "yes":
        if not await executor.approve_plan(goal_id):
            await conn_mgr.send_frame(
                {"type": "error", "detail": "Goal is not awaiting approval."}, thread_id
            )
            return
        await _reply(
            container,
            conn_mgr,
            f"Started <b>{title}</b> — Ze is working on the first milestone.",
            thread_id,
        )
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    elif action == "no":
        if not await executor.reject_plan(goal_id):
            await conn_mgr.send_frame(
                {"type": "error", "detail": "Goal is not awaiting approval."}, thread_id
            )
            return
        await _reply(container, conn_mgr, f"Cancelled <b>{title}</b>.", thread_id)
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    else:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Unrecognised action."}, thread_id
        )


async def _handle_gate_action(
    container: Any,
    conn_mgr: ConnectionManager,
    executor: Any,
    store: Any,
    action: str,
    gate_id_str: str,
    thread_id: str | None,
) -> None:
    gate_id = UUID(gate_id_str)
    gate = await store.get_gate(gate_id)
    if gate is None:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Checkpoint not found."}, thread_id
        )
        return

    goal = await store.get_goal(gate.goal_id)
    title = html.escape(goal.title) if goal else "goal"

    if action == "approve":
        await executor.handle_gate_approved(gate_id)
        await _reply(
            container,
            conn_mgr,
            f"Approved — Ze will continue <b>{title}</b>.",
            thread_id,
        )
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    elif action == "stop":
        await executor.handle_gate_stopped(gate_id)
        await _reply(container, conn_mgr, f"Stopped <b>{title}</b>.", thread_id)
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    elif action == "redirect":
        if thread_id:
            conn_mgr.set_pending_gate_redirect(gate_id, thread_id)
        await _reply(
            container,
            conn_mgr,
            f"Send your instructions for <b>{title}</b> and I'll redirect from this checkpoint.",
            thread_id,
        )
    else:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Unrecognised action."}, thread_id
        )


async def _handle_stuck_action(
    container: Any,
    conn_mgr: ConnectionManager,
    executor: Any,
    store: Any,
    action: str,
    goal_id_hex: str,
    thread_id: str | None,
) -> None:
    goal_id = UUID(hex=goal_id_hex)
    goal = await store.get_goal(goal_id)
    if goal is None:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Goal not found."}, thread_id
        )
        return

    title = html.escape(goal.title)

    if action == "redirect":
        await _reply(
            container,
            conn_mgr,
            f"Send me your instructions for <b>{title}</b> and I'll redirect it right away.",
            thread_id,
        )
        return

    if action == "pause":
        if goal.status not in (GoalStatus.ACTIVE, GoalStatus.AWAITING_GATE):
            await conn_mgr.send_frame(
                {"type": "error", "detail": "Goal already resolved."}, thread_id
            )
            return
        await store.update_status(goal_id, GoalStatus.PAUSED)
        await _reply(
            container,
            conn_mgr,
            f"Paused <b>{title}</b>. Resume it any time by telling me.",
            thread_id,
        )
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
        return

    if action == "abandon":
        if goal.status in (GoalStatus.COMPLETED, GoalStatus.ABANDONED):
            await conn_mgr.send_frame(
                {"type": "error", "detail": "Goal already resolved."}, thread_id
            )
            return
        await store.update_status(goal_id, GoalStatus.ABANDONED)
        await _reply(container, conn_mgr, f"Abandoned <b>{title}</b>.", thread_id)
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
        return

    gate = await store.get_pending_gate(goal_id)
    if gate is None:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Checkpoint already resolved."}, thread_id
        )
        return

    if action == "gate_approve":
        await executor.handle_gate_approved(gate.id)
        await _reply(
            container,
            conn_mgr,
            f"Approved — Ze will continue <b>{title}</b>.",
            thread_id,
        )
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    elif action == "gate_stop":
        await executor.handle_gate_stopped(gate.id)
        await _reply(container, conn_mgr, f"Stopped <b>{title}</b>.", thread_id)
        await conn_mgr.send_frame({"type": "refresh", "screen": "goals"}, thread_id)
    else:
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Unrecognised action."}, thread_id
        )


async def _reply(
    container: Any,
    conn_mgr: ConnectionManager,
    text: str,
    thread_id: str | None,
) -> None:
    if thread_id:
        await container.interface.send_with_thread(text, thread_id=thread_id)
    else:
        await container.interface.send(OutboundMessage(content=text, format="html"))
