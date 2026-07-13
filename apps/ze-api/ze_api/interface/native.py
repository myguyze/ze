from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from uuid import uuid4

from ze_agents.interface.types import (
    Action,
    ConfirmationRequest,
    Notification,
    OutboundMessage,
)
from ze_core.conversation.messages import Message
from ze_logging import get_logger

if TYPE_CHECKING:
    from ze_notifications.notifier import Notifier as PushNotifier
    from ze_core.conversation.messages import MessageStore
    from ze_api.api.websocket.connection import ConnectionManager

log = get_logger(__name__)

_NTFY_PRIORITY_MAP = {"normal": 3, "high": 5}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DANGER_LABELS = frozenset({"stop", "cancel", "abandon", "dismiss"})


class NativeAppInterface:
    """AppInterface for the web client — WebSocket + ntfy delivery."""

    confirmation_style: ClassVar[Literal["inline", "async"]] = "async"

    def __init__(
        self,
        message_store: MessageStore,
        connection_manager: ConnectionManager,
        notifier: PushNotifier | None,
    ) -> None:
        self._store = message_store
        self._conn = connection_manager
        self._notifier = notifier

    async def send(self, message: OutboundMessage) -> None:
        await self._send_message(message.content)

    async def push(self, notification: Notification) -> None:
        await self._send_message(
            notification.content,
            ntfy_priority=_NTFY_PRIORITY_MAP.get(notification.urgency, 3),
        )
        if notification.actions:
            await self._send_action_request(notification)
        if notification.event_type is not None:
            await self._send_notification_frame(notification)

    async def send_trace_partial(
        self, message_id: str, fields: dict, thread_id: str | None = None
    ) -> None:
        try:
            await self._conn.send_frame(
                {
                    "type": "trace_update",
                    "message_id": message_id,
                    "partial": True,
                    "agent": "",
                    "routing_method": "",
                    "confidence": 0.0,
                    "score_gap": 0.0,
                    "is_compound": False,
                    "subtasks": [],
                    "memory_chunks": [],
                    "tool_calls": [],
                    "total_duration_ms": 0,
                    **fields,
                },
                thread_id,
            )
        except Exception as exc:
            log.warning("native_interface_trace_partial_failed", error=str(exc))

    async def _send_message(
        self,
        text: str,
        thread_id: str | None = None,
        components: list[dict] | None = None,
        ntfy_priority: int = 3,
        trace: Any | None = None,
        message_id: str | None = None,
    ) -> None:
        from uuid import UUID

        msg = Message(
            id=UUID(message_id) if message_id else uuid4(),
            role="assistant",
            text=text,
            components=components or [],
            read=False,
            created_at=datetime.now(timezone.utc),
            thread_id=thread_id,
        )
        try:
            await self._store.save(msg)
        except Exception as exc:
            log.warning("native_interface_save_failed", error=str(exc))

        if trace is not None:
            try:
                await self._store.save_trace(msg.id, trace)
            except Exception as exc:
                log.warning("native_interface_save_trace_failed", error=str(exc))
            try:
                from dataclasses import asdict

                await self._conn.send_frame(
                    {
                        "type": "trace_update",
                        "message_id": str(msg.id),
                        **asdict(trace),
                    },
                    thread_id,
                )
            except Exception as exc:
                log.warning("native_interface_trace_update_failed", error=str(exc))

        try:
            await self._conn.push(msg, thread_id)
        except Exception as exc:
            log.warning("native_interface_push_failed", error=str(exc))

        # Only push via ntfy when the WebSocket is not connected — the client is
        # receiving frames in real-time when connected, so a push notification
        # would be redundant noise.
        if self._notifier is not None and not self._conn.connected:
            from ze_notifications.types import Notification as PushNotification

            try:
                await self._notifier.push(
                    PushNotification(
                        title="Ze",
                        body=text[:200],
                        priority=ntfy_priority,
                    )
                )
            except Exception as exc:
                log.warning("native_interface_ntfy_failed", error=str(exc))

    async def send_with_thread(
        self,
        text: str,
        thread_id: str | None,
        components: list[dict] | None = None,
        trace: Any | None = None,
        message_id: str | None = None,
    ) -> None:
        """Called by the WS handler after graph invocation to attach the thread_id."""
        await self._send_message(
            text,
            thread_id=thread_id,
            components=components,
            trace=trace,
            message_id=message_id,
        )

    async def send_confirmation(self, request: ConfirmationRequest) -> None:
        """Deliver a confirmation UI frame over WebSocket (and ntfy if backgrounded)."""
        actions = _confirmation_actions(request.options)
        await self._conn.send_frame(
            {
                "type": "confirm_request",
                "id": str(uuid4()),
                "prompt": request.content,
                "actions": actions,
            }
        )

        if self._notifier is not None and not self._conn.connected:
            from ze_notifications.types import Notification as PushNotification

            body = (
                f"Ze needs your approval:\n{request.content}"
                if request.content
                else "Ze needs your approval."
            )
            try:
                await self._notifier.push(
                    PushNotification(title="Ze", body=body[:200], priority=5)
                )
            except Exception as exc:
                log.warning("native_interface_confirmation_ntfy_failed", error=str(exc))

    async def _send_notification_frame(self, notification: Notification) -> None:
        try:
            await self._conn.send_frame(
                {
                    "type": "notification",
                    "id": notification.id,
                    "event_type": notification.event_type,
                    "source": notification.source,
                    "title": notification.title,
                    "body": notification.content,
                    "target_type": notification.target_type,
                    "target_id": notification.target_id,
                    "created_at": notification.created_at.isoformat()
                    if notification.created_at
                    else None,
                    "read": False,
                }
            )
        except Exception as exc:
            log.warning("native_interface_notification_frame_failed", error=str(exc))

    async def _send_action_request(self, notification: Notification) -> None:
        prompt = (
            _strip_html(notification.content)
            if notification.format == "html"
            else notification.content
        )
        await self._conn.send_frame(
            {
                "type": "confirm_request",
                "id": str(uuid4()),
                "prompt": prompt,
                "actions": [
                    _action_to_frame(action) for action in notification.actions
                ],
            }
        )


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text).strip()


def _action_to_frame(action: Action) -> dict[str, str]:
    label_key = action.label.lower()
    if any(word in label_key for word in _DANGER_LABELS):
        style = "danger"
    elif action.row == 0:
        style = "primary"
    else:
        style = "secondary"
    return {"label": action.label, "value": action.payload, "style": style}


def _confirmation_actions(options: list[str]) -> list[dict[str, str]]:
    if options == ["Approve", "Cancel"]:
        return [
            {"label": "Approve", "value": "approve", "style": "primary"},
            {"label": "Cancel", "value": "deny", "style": "secondary"},
        ]
    return [{"label": opt, "value": opt.lower()} for opt in options]
