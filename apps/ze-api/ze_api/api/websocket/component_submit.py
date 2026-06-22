from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.onboarding import send_onboarding_view
from ze_api.api.websocket.turns import handle_message
from ze_api.errors import OnboardingError
from ze_logging import get_logger

log = get_logger(__name__)


async def handle_component_submit(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
    msg_store: Any,
    pending_config: dict | None,
    *,
    confirmation_store: Any | None = None,
    session_store: Any | None = None,
) -> dict | None:
    step_id = str(data.get("step_id") or data.get("component_id") or "")
    values = data.get("values") or {}
    if not step_id or not isinstance(values, dict):
        await conn_mgr.send_frame({
            "type": "error",
            "detail": "component_submit requires step_id and object values",
        })
        return pending_config

    session_id_raw = data.get("session_id")
    if session_id_raw:
        try:
            session_id = UUID(str(session_id_raw))
            view = await container.onboarding_coordinator.submit(
                session_id=session_id,
                step_id=step_id,
                values=values,
            )
            await send_onboarding_view(conn_mgr, view)
            return pending_config
        except OnboardingError:
            pass
        except ValueError:
            pass
        except Exception as exc:
            log.warning("ws_component_submit_onboarding_failed", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Could not submit component."})
            return pending_config

    thread_id = data.get("thread_id") or conn_mgr.thread_id
    if not thread_id:
        await conn_mgr.send_frame({"type": "error", "detail": "thread_id required"})
        return pending_config

    text = f"[component_submit:{step_id}] {json.dumps(values)}"
    return await handle_message(
        ws,
        {"type": "message", "text": text, "thread_id": thread_id},
        container,
        msg_store,
        conn_mgr,
        pending_config,
        confirmation_store=confirmation_store,
        session_store=session_store,
    )
