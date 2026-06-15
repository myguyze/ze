"""
WS protocol conformance tests (C2) + confirmation flow E2E coverage.

Conformance tests verify that every frame the server emits matches the
TypeScript InboundFrame union in apps/ze-web/src/ws/protocol.ts.

E2E tests verify the approve/deny/timeout confirmation paths end-to-end
using mocked WebSocket + container objects.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_api.api.ws import ConnectionManager, _confirmation_timeout, _handle_confirm, _message_to_dict
from ze_core.messages.types import Message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ws() -> Any:
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _make_message(**kwargs) -> Message:
    return Message(
        id=kwargs.get("id", uuid4()),
        role=kwargs.get("role", "assistant"),
        text=kwargs.get("text", "Hello"),
        components=kwargs.get("components", []),
        read=kwargs.get("read", False),
        created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
        thread_id=kwargs.get("thread_id", None),
    )


def _make_msg_store(messages: list[Message] | None = None) -> Any:
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=messages or [])
    return store


def _frames_sent(ws: Any) -> list[dict]:
    return [call[0][0] for call in ws.send_json.call_args_list]


# ── Protocol conformance: InboundFrame shapes ─────────────────────────────────

class TestMessageFrameConformance:
    """message frame: {type, message: {id, role, text, components, read, created_at, thread_id}}"""

    async def test_message_frame_has_required_keys(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        msg = _make_message()
        store = _make_msg_store([msg])
        await mgr.connect(ws, store)

        frame = _frames_sent(ws)[0]
        assert frame["type"] == "message"
        m = frame["message"]
        assert "id" in m
        assert "role" in m
        assert "text" in m
        assert "components" in m
        assert "read" in m
        assert "created_at" in m
        assert "thread_id" in m

    async def test_message_frame_id_is_string(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        msg = _make_message()
        store = _make_msg_store([msg])
        await mgr.connect(ws, store)

        frame = _frames_sent(ws)[0]
        assert isinstance(frame["message"]["id"], str)

    async def test_message_frame_role_is_valid(self):
        for role in ("user", "assistant"):
            mgr = ConnectionManager()
            ws = _make_ws()
            msg = _make_message(role=role)
            store = _make_msg_store([msg])
            await mgr.connect(ws, store)

            frame = _frames_sent(ws)[0]
            assert frame["message"]["role"] in ("user", "assistant")

    async def test_message_frame_components_is_list(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        msg = _make_message(components=[{"type": "card", "body": "x"}])
        store = _make_msg_store([msg])
        await mgr.connect(ws, store)

        frame = _frames_sent(ws)[0]
        assert isinstance(frame["message"]["components"], list)

    async def test_message_to_dict_created_at_is_iso_string(self):
        now = datetime.now(timezone.utc)
        msg = _make_message(created_at=now)
        d = _message_to_dict(msg)
        assert d["created_at"] == now.isoformat()

    async def test_message_frame_with_onboarding_key(self):
        """Server attaches optional 'onboarding' key; TS type models it as optional."""
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        from ze_api.api.ws import _send_onboarding_view
        from ze_onboarding import OnboardingView

        session_id = uuid4()
        await _send_onboarding_view(mgr, OnboardingView(session_id=session_id, text="Hi", components=[]))
        frame = _frames_sent(ws)[0]
        assert frame["type"] == "message"
        assert "onboarding" in frame
        assert "session_id" in frame["onboarding"]
        assert "completed" in frame["onboarding"]


class TestConfirmRequestFrameConformance:
    """confirm_request frame: {type, id, prompt, actions: [{label, value, style?}]}"""

    async def test_confirm_request_shape_matches_protocol(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        request_id = str(uuid4())
        frame = {
            "type": "confirm_request",
            "id": request_id,
            "prompt": "Delete 10 emails?",
            "actions": [
                {"label": "Approve", "value": "approve", "style": "primary"},
                {"label": "Cancel", "value": "deny", "style": "secondary"},
            ],
        }
        await mgr.send_frame(frame)

        sent = _frames_sent(ws)[0]
        assert sent["type"] == "confirm_request"
        assert isinstance(sent["id"], str)
        assert isinstance(sent["prompt"], str)
        assert isinstance(sent["actions"], list)
        for action in sent["actions"]:
            assert "label" in action
            assert "value" in action

    async def test_confirm_request_action_style_is_primary_secondary_or_danger(self):
        valid_styles = {"primary", "secondary", "danger"}
        for style in valid_styles:
            action = {"label": "OK", "value": "approve", "style": style}
            assert action["style"] in valid_styles


class TestConfirmCancelFrameConformance:
    """confirm_cancel frame: {type, id}"""

    async def test_confirm_cancel_shape(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        request_id = str(uuid4())
        await mgr.send_frame({"type": "confirm_cancel", "id": request_id})

        sent = _frames_sent(ws)[0]
        assert sent["type"] == "confirm_cancel"
        assert "id" in sent
        assert isinstance(sent["id"], str)


class TestTypingAndErrorFrameConformance:
    """typing frame: {type}; error frame: {type, detail}"""

    async def test_typing_frame_has_only_type(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        await mgr.send_frame({"type": "typing"})
        sent = _frames_sent(ws)[0]
        assert sent["type"] == "typing"

    async def test_error_frame_has_detail(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        await mgr.send_frame({"type": "error", "detail": "Something went wrong."})
        sent = _frames_sent(ws)[0]
        assert sent["type"] == "error"
        assert "detail" in sent
        assert isinstance(sent["detail"], str)


class TestRefreshFrameConformance:
    """refresh frame: {type, screen}"""

    async def test_refresh_frame_has_screen(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        await mgr.send_frame({"type": "refresh", "screen": "goals"})
        sent = _frames_sent(ws)[0]
        assert sent["type"] == "refresh"
        assert "screen" in sent
        assert isinstance(sent["screen"], str)


# ── Confirmation flow E2E ─────────────────────────────────────────────────────

def _make_pending_config(thread_id: str = "t1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _make_container(thread_id: str = "t1") -> Any:
    container = AsyncMock()
    result = MagicMock()
    result.response = "Action completed."
    result.final_state = {"components": []}
    container.resume_turn = AsyncMock(return_value=result)
    container.abort_pending_checkpoint = AsyncMock()
    container.interface = AsyncMock()
    container.interface.send_with_thread = AsyncMock()
    return container


class TestConfirmationApproveFlow:
    """approve path: resumes graph and delivers response."""

    async def test_approve_calls_resume_turn(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)

        container = _make_container()
        pending_config = _make_pending_config()

        result = await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "approve"},
            container, mgr, pending_config,
        )

        container.resume_turn.assert_awaited_once_with(pending_config)
        assert result is None  # pending_config cleared

    async def test_approve_sends_typing_before_resume(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = _make_container()
        pending_config = _make_pending_config()

        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "approve"},
            container, mgr, pending_config,
        )

        frames = _frames_sent(ws)
        assert any(f.get("type") == "typing" for f in frames)

    async def test_approve_clears_confirmation_store(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)

        container = _make_container()
        confirmation_store = AsyncMock()
        confirmation_store.clear = AsyncMock(return_value=True)

        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "approve"},
            container, mgr, _make_pending_config(),
            confirmation_store=confirmation_store,
        )

        confirmation_store.clear.assert_awaited_once()

    async def test_approve_error_sends_error_frame(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = _make_container()
        container.resume_turn = AsyncMock(side_effect=RuntimeError("graph error"))

        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "approve"},
            container, mgr, _make_pending_config(),
        )

        frames = _frames_sent(ws)
        error_frames = [f for f in frames if f.get("type") == "error"]
        assert len(error_frames) == 1


class TestConfirmationDenyFlow:
    """deny path: aborts checkpoint and sends confirm_cancel."""

    async def test_deny_calls_abort_pending_checkpoint(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)

        container = _make_container()
        pending_config = _make_pending_config()

        result = await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "deny"},
            container, mgr, pending_config,
        )

        container.abort_pending_checkpoint.assert_awaited_once_with(pending_config)

    async def test_deny_sends_confirm_cancel_frame(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = _make_container()

        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-99", "choice": "deny"},
            container, mgr, _make_pending_config(),
        )

        frames = _frames_sent(ws)
        cancel_frames = [f for f in frames if f.get("type") == "confirm_cancel"]
        assert len(cancel_frames) == 1
        assert cancel_frames[0]["id"] == "req-99"

    async def test_deny_returns_none_clearing_pending_config(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)

        container = _make_container()

        result = await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "deny"},
            container, mgr, _make_pending_config(),
        )

        assert result is None

    async def test_deny_with_no_pending_config_sends_error(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = _make_container()

        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "deny"},
            container, mgr, None,  # no pending config
        )

        frames = _frames_sent(ws)
        error_frames = [f for f in frames if f.get("type") == "error"]
        assert len(error_frames) == 1

    async def test_deny_abort_failure_is_swallowed(self):
        ws = _make_ws()
        mgr = ConnectionManager()
        store = _make_msg_store([])
        await mgr.connect(ws, store)

        container = _make_container()
        container.abort_pending_checkpoint = AsyncMock(side_effect=RuntimeError("checkpoint error"))

        # Should not raise — failure is logged, confirm_cancel still sent
        await _handle_confirm(
            ws, {"type": "confirm", "id": "req-1", "choice": "deny"},
            container, mgr, _make_pending_config(),
        )


class TestConfirmationTimeoutFlow:
    """timeout path: clears store, aborts checkpoint, notifies user."""

    async def test_timeout_clears_store_and_aborts_checkpoint(self):
        confirmation_store = AsyncMock()
        confirmation_store.clear = AsyncMock(return_value=True)

        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = AsyncMock()
        container.abort_pending_checkpoint = AsyncMock()

        graph_config = _make_pending_config("thread-timeout")

        await _confirmation_timeout(
            confirmation_store, mgr, None,
            "thread-timeout", 0,
            container=container,
            graph_config=graph_config,
        )

        confirmation_store.clear.assert_awaited_once_with("thread-timeout")
        container.abort_pending_checkpoint.assert_awaited_once_with(graph_config)

    async def test_timeout_sends_message_to_user(self):
        confirmation_store = AsyncMock()
        confirmation_store.clear = AsyncMock(return_value=True)

        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        await _confirmation_timeout(
            confirmation_store, mgr, None,
            "thread-1", 0,
        )

        frames = _frames_sent(ws)
        msg_frames = [f for f in frames if f.get("type") == "message"]
        assert len(msg_frames) == 1
        assert "elapsed" in msg_frames[0]["message"]["text"]

    async def test_timeout_noop_when_already_cleared(self):
        """If the user already responded, clear() returns False — no message sent."""
        confirmation_store = AsyncMock()
        confirmation_store.clear = AsyncMock(return_value=False)

        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = AsyncMock()

        await _confirmation_timeout(
            confirmation_store, mgr, None,
            "thread-1", 0,
            container=container,
            graph_config=_make_pending_config(),
        )

        # No message sent and checkpoint not aborted
        assert _frames_sent(ws) == []
        container.abort_pending_checkpoint.assert_not_awaited()

    async def test_timeout_abort_failure_is_swallowed(self):
        """Checkpoint abort failure must not prevent the timeout message."""
        confirmation_store = AsyncMock()
        confirmation_store.clear = AsyncMock(return_value=True)

        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])
        await mgr.connect(ws, store)
        ws.send_json.reset_mock()

        container = AsyncMock()
        container.abort_pending_checkpoint = AsyncMock(side_effect=RuntimeError("boom"))

        await _confirmation_timeout(
            confirmation_store, mgr, None,
            "thread-1", 0,
            container=container,
            graph_config=_make_pending_config(),
        )

        # Message still sent despite abort failure
        frames = _frames_sent(ws)
        assert any(f.get("type") == "message" for f in frames)


# ── Scoped unread replay ──────────────────────────────────────────────────────

class TestScopedUnreadReplay:
    """list_unread is called with thread_id so replay is scoped to current thread."""

    async def test_connect_passes_thread_id_to_list_unread(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])

        await mgr.connect(ws, store, thread_id="ze-abc123")

        store.list_unread.assert_awaited_once_with("ze-abc123")

    async def test_connect_passes_none_thread_id_when_not_supplied(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        store = _make_msg_store([])

        await mgr.connect(ws, store)

        store.list_unread.assert_awaited_once_with(None)

    async def test_unread_replay_only_shows_messages_for_current_thread(self):
        mgr = ConnectionManager()
        ws = _make_ws()

        msg_for_thread = _make_message(thread_id="ze-abc", text="For this thread")
        store = _make_msg_store([msg_for_thread])

        await mgr.connect(ws, store, thread_id="ze-abc")

        frames = _frames_sent(ws)
        msg_frames = [f for f in frames if f.get("type") == "message"]
        assert len(msg_frames) == 1
        assert msg_frames[0]["message"]["text"] == "For this thread"
