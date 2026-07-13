from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from ze_api.api.websocket.commands import handle_command
from ze_api.api.websocket.component_submit import handle_component_submit
from ze_api.api.websocket.confirmation import handle_confirm
from ze_api.api.websocket.goal_actions import handle_action
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.onboarding import send_onboarding_view
from ze_api.api.websocket.turns import handle_message
from ze_logging import get_logger

log = get_logger(__name__)


async def websocket_endpoint(
    ws: WebSocket,
    token: str | None = None,
) -> None:
    settings = ws.app.state.settings
    api_key: str = settings.ze_api_key

    auth_header = ws.headers.get("Authorization", "")
    bearer = (
        auth_header.removeprefix("Bearer ").strip()
        if auth_header.startswith("Bearer ")
        else ""
    )

    if bearer != api_key and token != api_key:
        await ws.close(code=4001)
        return

    await ws.accept()

    container = ws.app.state.container
    conn_mgr: ConnectionManager = container.connection_manager
    msg_store = container.message_store
    confirmation_store = container.confirmation_store
    session_store = container.session_store

    await conn_mgr.connect(ws, msg_store, confirmation_store)
    log.info("ws_connected")

    onboarding_cfg = settings.config.get("onboarding", {})
    if onboarding_cfg.get("enabled", True) and onboarding_cfg.get(
        "auto_start_on_empty_profile",
        True,
    ):
        try:
            view = await container.onboarding_coordinator.start_if_needed()
            if view is not None:
                await send_onboarding_view(conn_mgr, view)
        except Exception as exc:
            log.warning("ws_onboarding_autostart_failed", error=str(exc))

    # Per-thread LangGraph configs for in-flight confirmations.
    # Keyed by thread_id; each value is the graph config needed to resume.
    pending_configs: dict[str, dict] = {}

    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break

            frame_type = data.get("type")

            if frame_type == "ping":
                await ws.send_json({"type": "pong"})

            elif frame_type == "ack":
                ids: list[UUID] = []
                for raw in data.get("ids") or []:
                    if not raw:
                        continue
                    try:
                        ids.append(UUID(str(raw)))
                    except (TypeError, ValueError):
                        log.warning("ws_ack_invalid_id", id=raw)
                await msg_store.mark_read(ids)

            elif frame_type == "command":
                # Commands are not per-thread (they operate on global session state).
                # Pass the first pending config for compatibility with cancel command.
                first_pending = next(iter(pending_configs.values()), None)
                new_pending = await handle_command(
                    ws, data, container, conn_mgr, first_pending
                )
                if new_pending is None and first_pending is not None:
                    pending_configs.clear()

            elif frame_type == "component_submit":
                thread_id = data.get("thread_id") or ""
                if not thread_id:
                    await ws.send_json(
                        {"type": "error", "detail": "thread_id required"}
                    )
                    continue
                if not conn_mgr.try_set_busy(thread_id):
                    await conn_mgr.send_frame(
                        {"type": "error", "detail": "busy"}, thread_id
                    )
                    continue
                try:
                    result = await handle_component_submit(
                        ws,
                        data,
                        container,
                        conn_mgr,
                        msg_store,
                        pending_configs.get(thread_id),
                        confirmation_store=confirmation_store,
                        session_store=session_store,
                    )
                    if result is not None:
                        pending_configs[thread_id] = result
                    else:
                        pending_configs.pop(thread_id, None)
                finally:
                    conn_mgr.clear_busy(thread_id)

            elif frame_type == "confirm":
                thread_id = data.get("thread_id") or ""
                if not thread_id:
                    await ws.send_json(
                        {"type": "error", "detail": "thread_id required in confirm"}
                    )
                    continue
                result = await handle_confirm(
                    ws,
                    data,
                    container,
                    conn_mgr,
                    pending_configs.get(thread_id),
                    thread_id=thread_id,
                    confirmation_store=confirmation_store,
                    session_store=session_store,
                    msg_store=msg_store,
                )
                if result is not None:
                    pending_configs[thread_id] = result
                else:
                    pending_configs.pop(thread_id, None)

            elif frame_type == "action":
                await handle_action(ws, data, container, conn_mgr)

            elif frame_type == "message":
                thread_id = data.get("thread_id") or ""
                if not thread_id:
                    await ws.send_json(
                        {"type": "error", "detail": "thread_id required"}
                    )
                    continue
                if not conn_mgr.try_set_busy(thread_id):
                    await conn_mgr.send_frame(
                        {"type": "error", "detail": "busy"}, thread_id
                    )
                    continue

                # Spawn a background task so the WS loop can immediately accept
                # messages for other threads while this LLM call is in progress.
                asyncio.create_task(
                    _run_message_task(
                        ws,
                        data,
                        container,
                        msg_store,
                        conn_mgr,
                        pending_configs,
                        thread_id,
                        confirmation_store=confirmation_store,
                        session_store=session_store,
                    )
                )

    except Exception as exc:
        log.exception("ws_handler_error", error=str(exc))
    finally:
        await conn_mgr.disconnect()
        log.info("ws_disconnected")


async def _run_message_task(
    ws: WebSocket,
    data: dict,
    container: object,
    msg_store: object,
    conn_mgr: ConnectionManager,
    pending_configs: dict[str, dict],
    thread_id: str,
    *,
    confirmation_store: object | None,
    session_store: object | None,
) -> None:
    """Background task wrapper: runs handle_message and clears the busy flag."""
    try:
        result = await handle_message(
            ws,
            data,
            container,
            msg_store,
            conn_mgr,
            pending_configs.get(thread_id),
            confirmation_store=confirmation_store,
            session_store=session_store,
        )
        if result is not None:
            pending_configs[thread_id] = result
        else:
            pending_configs.pop(thread_id, None)
    except Exception as exc:
        log.exception("ws_message_task_error", thread_id=thread_id, error=str(exc))
        await conn_mgr.send_frame(
            {"type": "error", "detail": "Something went wrong."}, thread_id
        )
    finally:
        conn_mgr.clear_busy(thread_id)
