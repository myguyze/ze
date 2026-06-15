from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.onboarding import send_onboarding_view
from ze_api.logging import get_logger

log = get_logger(__name__)


def build_capabilities_summary() -> str:
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


async def handle_command(
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
            await conn_mgr.send_frame({
                "type": "message",
                "message": {"role": "assistant", "text": summary, "components": []},
            })
        except Exception as exc:
            log.warning("ws_costs_command_failed", error=str(exc))
        return pending_config

    if name == "status":
        from ze_api.api.routes.costs import _build_status_summary
        period_days = int(data.get("period_days", 1))
        try:
            summary = await _build_status_summary(container, period_days=period_days)
            await conn_mgr.send_frame({
                "type": "message",
                "message": {"role": "assistant", "text": summary, "components": []},
            })
        except Exception as exc:
            log.warning("ws_status_command_failed", error=str(exc))
        return pending_config

    if name == "onboarding":
        try:
            view = await container.onboarding_coordinator.start()
            await send_onboarding_view(conn_mgr, view)
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
            summary = build_capabilities_summary()
            await conn_mgr.send_frame({
                "type": "message",
                "message": {"role": "assistant", "text": summary, "components": []},
            })
        except Exception as exc:
            log.warning("ws_capabilities_command_failed", error=str(exc))
        return pending_config

    log.warning("ws_unknown_command", name=name)
    return pending_config
