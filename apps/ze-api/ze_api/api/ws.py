from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ze_core.messages.types import Message
from ze_agents.interface.types import RawInput
from ze_api.errors import OnboardingError
from ze_api.logging import get_logger
from ze_onboarding import OnboardingView

log = get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Holds the single active WebSocket connection."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._lock = asyncio.Lock()
        self._busy = False

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(
        self,
        ws: WebSocket,
        message_store: Any,
        confirmation_store: Any | None = None,
    ) -> None:
        async with self._lock:
            if self._ws is not None:
                try:
                    await self._ws.close(code=4000)
                except Exception:
                    pass
            self._ws = ws
            self._busy = False

        unread = await message_store.list_unread()
        async with self._lock:
            for msg in unread:
                try:
                    await self._ws.send_json({"type": "message", "message": _message_to_dict(msg)})
                except Exception:
                    self._ws = None
                    break

        # Replay any pending confirmation that survived the reconnect.
        if confirmation_store is not None:
            try:
                pending = await confirmation_store.get_any_pending()
                if pending is not None:
                    async with self._lock:
                        if self._ws is not None:
                            try:
                                await self._ws.send_json({
                                    "type": "confirm_request",
                                    "id": pending["request_id"],
                                    "prompt": pending["prompt"],
                                    "actions": pending["actions"],
                                })
                            except Exception as exc:
                                log.warning("ws_confirmation_replay_failed", error=str(exc))
            except Exception as exc:
                log.warning("ws_confirmation_replay_error", error=str(exc))

    async def disconnect(self) -> None:
        async with self._lock:
            self._ws = None

    async def push(self, message: Message) -> None:
        """Send a message frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json({"type": "message", "message": _message_to_dict(message)})
            except Exception as exc:
                log.warning("ws_push_failed", error=str(exc))
                self._ws = None

    async def send_frame(self, frame: dict) -> None:
        """Send an arbitrary JSON frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json(frame)
            except Exception as exc:
                log.warning("ws_send_frame_failed", error=str(exc))
                self._ws = None

    def try_set_busy(self) -> bool:
        """Attempt to claim the invocation slot. Returns True on success."""
        if self._busy:
            return False
        self._busy = True
        return True

    def clear_busy(self) -> None:
        self._busy = False


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str | None = None) -> None:
    settings = ws.app.state.settings
    api_key: str = settings.ze_api_key

    auth_header = ws.headers.get("Authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

    if bearer != api_key and token != api_key:
        await ws.close(code=4001)
        return

    await ws.accept()

    conn_mgr: ConnectionManager = ws.app.state.connection_manager
    msg_store = ws.app.state.message_store
    container = ws.app.state.container
    confirmation_store = getattr(ws.app.state, "confirmation_store", None)
    session_store = getattr(ws.app.state, "session_store", None)

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
                await _send_onboarding_view(conn_mgr, view)
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
                ids = [UUID(i) for i in data.get("ids", [])]
                await msg_store.mark_read(ids)

            elif frame_type == "command":
                pending_config = await _handle_command(
                    ws, data, container, conn_mgr, pending_config
                )

            elif frame_type == "component_submit":
                if not conn_mgr.try_set_busy():
                    await ws.send_json({"type": "error", "detail": "busy"})
                    continue
                try:
                    await _handle_component_submit(data, container, conn_mgr)
                finally:
                    conn_mgr.clear_busy()

            elif frame_type == "confirm":
                pending_config = await _handle_confirm(
                    ws, data, container, conn_mgr, pending_config,
                    confirmation_store=confirmation_store,
                    session_store=session_store,
                )

            elif frame_type == "message":
                if not conn_mgr.try_set_busy():
                    await ws.send_json({"type": "error", "detail": "busy"})
                    continue

                try:
                    pending_config = await _handle_message(
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


async def _handle_message(
    ws: WebSocket,
    data: dict,
    container: Any,
    msg_store: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
    *,
    confirmation_store: Any | None = None,
    session_store: Any | None = None,
) -> dict | None:
    text: str = data.get("text", "")
    thread_id: str | None = data.get("thread_id") or None
    context: dict | None = data.get("context") or None

    if not text:
        return pending_config

    user_msg = Message(
        id=uuid4(),
        role="user",
        text=text,
        components=[],
        read=True,
        created_at=datetime.now(timezone.utc),
        thread_id=thread_id,
    )
    try:
        await msg_store.save(user_msg)
    except Exception as exc:
        log.warning("ws_save_user_msg_failed", error=str(exc))

    if session_store is not None and thread_id:
        title = text[:60].strip() if text else None
        try:
            await session_store.upsert(thread_id, title=title)
        except Exception as exc:
            log.warning("ws_session_upsert_failed", error=str(exc))

    await conn_mgr.send_frame({"type": "typing"})

    config_extra: dict = {}
    if context:
        config_extra["screen_context"] = context
    if thread_id:
        config_extra["thread_id"] = thread_id

    try:
        outcome = await container.invoke_raw_turn(
            thread_id or f"ws-{uuid4()}",
            RawInput(text=text),
            config_extra=config_extra,
        )
    except Exception as exc:
        log.exception("ws_invoke_error", error=str(exc))
        await conn_mgr.send_frame({"type": "error", "detail": "Something went wrong."})
        return None

    if outcome.interrupted:
        request_id = str(uuid4())
        effective_thread_id = _extract_thread_id(outcome.config) or thread_id or ""
        confirm_timeout = getattr(container.settings, "confirm_timeout_seconds", 900)

        frame = {
            "type": "confirm_request",
            "id": request_id,
            "prompt": outcome.draft or "",
            "actions": [
                {"label": "Approve", "value": "approve", "style": "primary"},
                {"label": "Cancel", "value": "deny", "style": "secondary"},
            ],
        }

        # Persist so reconnecting clients receive the confirm_request again.
        if confirmation_store is not None and effective_thread_id:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=confirm_timeout)
            await confirmation_store.save(
                thread_id=effective_thread_id,
                request_id=request_id,
                prompt=outcome.draft or "",
                actions=frame["actions"],
                expires_at=expires_at,
            )

        await conn_mgr.send_frame(frame)

        # Push ntfy in case the app is backgrounded.
        notifier = getattr(container, "notifier", None)
        if notifier is not None:
            asyncio.create_task(_push_confirmation_ntfy(notifier, outcome.draft or ""))

        # Start timeout watchdog.
        if confirmation_store is not None and effective_thread_id:
            asyncio.create_task(_confirmation_timeout(
                confirmation_store,
                conn_mgr,
                notifier,
                effective_thread_id,
                confirm_timeout,
                container=container,
                graph_config=outcome.config,
            ))

        return outcome.config

    if outcome.response:
        # Clear any pending confirmation for this thread if the graph continued.
        effective_thread_id = _extract_thread_id(outcome.config) or thread_id or ""
        if confirmation_store is not None and effective_thread_id:
            await confirmation_store.clear(effective_thread_id)

        if session_store is not None and effective_thread_id:
            preview = outcome.response[:120].strip() if outcome.response else None
            try:
                await session_store.upsert(effective_thread_id, preview=preview)
            except Exception as exc:
                log.warning("ws_session_preview_update_failed", error=str(exc))

        components = outcome.final_state.get("components", [])
        await container.interface.send_with_thread(
            outcome.response,
            thread_id=_extract_thread_id(outcome.config),
            components=components or None,
        )

    return None


async def _handle_confirm(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
    *,
    confirmation_store: Any | None = None,
    session_store: Any | None = None,
) -> dict | None:
    choice = data.get("choice", "")
    request_id = data.get("id", "")

    if pending_config is None:
        await conn_mgr.send_frame({"type": "error", "detail": "No pending confirmation."})
        return None

    thread_id = _extract_thread_id(pending_config) or ""
    if confirmation_store is not None and thread_id:
        await confirmation_store.clear(thread_id)

    if choice == "approve":
        if not conn_mgr.try_set_busy():
            await conn_mgr.send_frame({"type": "error", "detail": "busy"})
            return pending_config
        try:
            await conn_mgr.send_frame({"type": "typing"})
            outcome = await container.resume_turn(pending_config)
        except Exception as exc:
            log.exception("ws_resume_error", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Resume failed."})
            return None
        finally:
            conn_mgr.clear_busy()

        if outcome.response:
            if session_store is not None and thread_id:
                preview = outcome.response[:120].strip()
                try:
                    await session_store.upsert(thread_id, preview=preview)
                except Exception as exc:
                    log.warning("ws_session_preview_update_failed", error=str(exc))

            components = outcome.final_state.get("components", [])
            await container.interface.send_with_thread(
                outcome.response,
                thread_id=thread_id,
                components=components or None,
            )
        return None
    else:
        try:
            await container.abort_pending_checkpoint(pending_config)
        except Exception as exc:
            log.warning("ws_deny_abort_failed", error=str(exc))
        await conn_mgr.send_frame({"type": "confirm_cancel", "id": request_id})
        return None


async def _push_confirmation_ntfy(notifier: Any, prompt: str) -> None:
    try:
        text = f"Ze needs your approval:\n{prompt}" if prompt else "Ze needs your approval."
        await notifier.push(text, urgency="high")
    except Exception as exc:
        log.warning("ws_confirmation_ntfy_failed", error=str(exc))


async def _confirmation_timeout(
    confirmation_store: Any,
    conn_mgr: ConnectionManager,
    notifier: Any | None,
    thread_id: str,
    timeout_seconds: int,
    container: Any | None = None,
    graph_config: dict | None = None,
) -> None:
    await asyncio.sleep(timeout_seconds)
    cleared = await confirmation_store.clear(thread_id)
    if not cleared:
        # User already responded or row was already gone.
        return

    log.info("confirmation_timeout_elapsed", thread_id=thread_id)

    if container is not None and graph_config is not None:
        try:
            await container.abort_pending_checkpoint(graph_config)
        except Exception as exc:
            log.warning("ws_timeout_checkpoint_abort_failed", error=str(exc))

    timeout_msg = (
        "I waited for your approval but the window elapsed — "
        "let me know if you'd like me to try again."
    )
    await conn_mgr.send_frame({
        "type": "message",
        "message": {"role": "assistant", "text": timeout_msg, "components": []},
    })
    if notifier is not None:
        try:
            await notifier.push(timeout_msg, urgency="low")
        except Exception as exc:
            log.warning("ws_timeout_ntfy_failed", error=str(exc))


async def _handle_command(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
) -> dict | None:
    name = data.get("name", "")

    if name == "cancel":
        if pending_config is not None:
            thread_id = pending_config.get("configurable", {}).get("thread_id", "")
            try:
                await container.abort_invocation(thread_id)
            except Exception as exc:
                log.warning("ws_cancel_abort_failed", error=str(exc))
            await conn_mgr.send_frame({"type": "confirm_cancel", "id": ""})
            return None
        return None

    if name == "costs":
        from ze_api.api.routes.costs import _build_cost_summary
        try:
            summary = await _build_cost_summary(container)
            await conn_mgr.send_frame({"type": "message", "message": {"role": "assistant", "text": summary, "components": []}})
        except Exception as exc:
            log.warning("ws_costs_command_failed", error=str(exc))
        return pending_config

    if name == "status":
        from ze_api.api.routes.costs import _build_status_summary
        period_days = int(data.get("period_days", 1))
        try:
            summary = await _build_status_summary(container, period_days=period_days)
            await conn_mgr.send_frame({"type": "message", "message": {"role": "assistant", "text": summary, "components": []}})
        except Exception as exc:
            log.warning("ws_status_command_failed", error=str(exc))
        return pending_config

    if name == "onboarding":
        try:
            view = await container.onboarding_coordinator.start()
            await _send_onboarding_view(conn_mgr, view)
        except Exception as exc:
            log.warning("ws_onboarding_command_failed", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Could not start onboarding."})
        return pending_config

    if name == "reset_preview":
        scope = data.get("scope", "memory")
        try:
            preview = await container.reset_service.preview(scope)
            lines = [f"{table}: {count}" for table, count in preview.counts.items()]
            text = "Reset preview:\n" + ("\n".join(lines) if lines else "Nothing to delete.")
            await conn_mgr.send_frame({
                "type": "message",
                "message": {"role": "assistant", "text": text, "components": []},
            })
        except Exception as exc:
            log.warning("ws_reset_preview_failed", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Could not preview reset."})
        return pending_config

    if name == "reset":
        scope = data.get("scope", "memory")
        confirm = data.get("confirm", "")
        try:
            result = await container.reset_service.reset(scope, confirm=confirm)
            lines = [f"{table}: {count}" for table, count in result.deleted.items()]
            text = "Reset complete:\n" + ("\n".join(lines) if lines else "Nothing was deleted.")
            await conn_mgr.send_frame({
                "type": "message",
                "message": {"role": "assistant", "text": text, "components": []},
            })
        except Exception as exc:
            log.warning("ws_reset_failed", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Could not reset state."})
        return pending_config

    if name == "capabilities":
        try:
            summary = _build_capabilities_summary()
            await conn_mgr.send_frame({"type": "message", "message": {"role": "assistant", "text": summary, "components": []}})
        except Exception as exc:
            log.warning("ws_capabilities_command_failed", error=str(exc))
        return pending_config

    log.warning("ws_unknown_command", name=name)
    return pending_config


def _build_capabilities_summary() -> str:
    from ze_agents.registry import get_registered_agents

    agents = get_registered_agents()
    lines: list[str] = ["Here's what I can help you with:\n"]
    for cls in sorted(agents.values(), key=lambda c: getattr(c, "display_name", "") or c.name):
        if not getattr(cls, "enabled", True):
            continue
        label = getattr(cls, "display_name", "") or cls.name.capitalize()
        raw = getattr(cls, "description", "").strip()
        summary = raw.splitlines()[0].strip() if raw else ""
        lines.append(f"**{label}** — {summary}")

    lines.append("\nJust ask — I'll figure out what to use.")
    return "\n".join(lines)


async def _handle_component_submit(
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
) -> None:
    try:
        session_id = UUID(str(data.get("session_id")))
        step_id = str(data.get("step_id") or data.get("component_id") or "")
        values = data.get("values") or {}
        if not step_id or not isinstance(values, dict):
            raise OnboardingError("component_submit requires step_id and object values")
        view = await container.onboarding_coordinator.submit(
            session_id=session_id,
            step_id=step_id,
            values=values,
        )
        await _send_onboarding_view(conn_mgr, view)
    except Exception as exc:
        log.warning("ws_component_submit_failed", error=str(exc))
        await conn_mgr.send_frame({"type": "error", "detail": "Could not submit component."})


async def _send_onboarding_view(
    conn_mgr: ConnectionManager,
    view: OnboardingView,
) -> None:
    await conn_mgr.send_frame({
        "type": "message",
        "message": {
            "id": str(uuid4()),
            "role": "assistant",
            "text": view.text,
            "components": view.components,
            "read": False,
            "thread_id": f"onboarding:{view.session_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "onboarding": {
            "session_id": str(view.session_id),
            "completed": view.completed,
        },
    })


def _extract_thread_id(config: dict) -> str | None:
    return config.get("configurable", {}).get("thread_id")


def _message_to_dict(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "role": msg.role,
        "text": msg.text,
        "components": msg.components,
        "read": msg.read,
        "thread_id": msg.thread_id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
