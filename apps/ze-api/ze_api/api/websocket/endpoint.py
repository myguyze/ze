from __future__ import annotations

from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from ze_api.api.websocket.commands import handle_command
from ze_api.api.websocket.component_submit import handle_component_submit
from ze_api.api.websocket.confirmation import handle_confirm
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.onboarding import send_onboarding_view
from ze_api.api.websocket.turns import handle_message
from ze_api.logging import get_logger

log = get_logger(__name__)


async def websocket_endpoint(
    ws: WebSocket,
    token: str | None = None,
    thread_id: str | None = None,
) -> None:
    settings = ws.app.state.settings
    api_key: str = settings.ze_api_key

    auth_header = ws.headers.get("Authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

    if bearer != api_key and token != api_key:
        await ws.close(code=4001)
        return

    await ws.accept()

    container = ws.app.state.container
    conn_mgr: ConnectionManager = container.connection_manager
    msg_store = container.message_store
    confirmation_store = container.confirmation_store
    session_store = container.session_store

    await conn_mgr.connect(ws, msg_store, confirmation_store, thread_id=thread_id)
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

    pending_config: dict | None = None

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
                pending_config = await handle_command(
                    ws, data, container, conn_mgr, pending_config
                )

            elif frame_type == "component_submit":
                if not conn_mgr.try_set_busy():
                    await ws.send_json({"type": "error", "detail": "busy"})
                    continue
                try:
                    pending_config = await handle_component_submit(
                        ws,
                        data,
                        container,
                        conn_mgr,
                        msg_store,
                        pending_config,
                        confirmation_store=confirmation_store,
                        session_store=session_store,
                    )
                finally:
                    conn_mgr.clear_busy()

            elif frame_type == "confirm":
                pending_config = await handle_confirm(
                    ws, data, container, conn_mgr, pending_config,
                    confirmation_store=confirmation_store,
                    session_store=session_store,
                )

            elif frame_type == "message":
                if not conn_mgr.try_set_busy():
                    await ws.send_json({"type": "error", "detail": "busy"})
                    continue

                try:
                    pending_config = await handle_message(
                        ws, data, container, msg_store, conn_mgr, pending_config,
                        confirmation_store=confirmation_store,
                        session_store=session_store,
                    )
                finally:
                    conn_mgr.clear_busy()

    except Exception as exc:
        log.exception("ws_handler_error", error=str(exc))
    finally:
        await conn_mgr.disconnect()
        log.info("ws_disconnected")
