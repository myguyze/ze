from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4


from ze_agents.errors import OnboardingError
from ze_api.api.websocket.component_submit import handle_component_submit
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.onboarding import send_onboarding_view
from ze_api.api.websocket.serializers import message_to_dict
from ze_onboarding import OnboardingView
from ze_core.conversation.messages import Message


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


def _make_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.headers = {}
    return ws


async def test_connection_manager_closes_first_on_second_connect():
    mgr = ConnectionManager()
    ws1 = _make_ws()
    ws2 = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    await mgr.connect(ws1, store)
    assert mgr.connected

    await mgr.connect(ws2, store)

    ws1.close.assert_called_once_with(code=4000)
    assert mgr.connected


async def test_connection_manager_flushes_unread_on_connect():
    mgr = ConnectionManager()
    ws = _make_ws()
    msg = _make_message(read=False)

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[msg])

    await mgr.connect(ws, store)

    ws.send_json.assert_called_once()
    frame = ws.send_json.call_args[0][0]
    assert frame["type"] == "message"
    assert frame["message"]["id"] == str(msg.id)


async def test_connection_manager_push_sends_message_frame():
    mgr = ConnectionManager()
    ws = _make_ws()
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])
    await mgr.connect(ws, store)

    msg = _make_message(text="Hey there")
    ws.send_json.reset_mock()
    await mgr.push(msg)

    ws.send_json.assert_called_once()
    frame = ws.send_json.call_args[0][0]
    assert frame["type"] == "message"
    assert frame["message"]["text"] == "Hey there"


async def test_connection_manager_push_noop_when_disconnected():
    mgr = ConnectionManager()
    msg = _make_message()

    # Should not raise — silently no-ops
    await mgr.push(msg)


async def test_connection_manager_disconnect_clears_connection():
    mgr = ConnectionManager()
    ws = _make_ws()
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])
    await mgr.connect(ws, store)

    await mgr.disconnect()

    assert not mgr.connected


async def test_connection_manager_busy_flag_per_thread():
    mgr = ConnectionManager()

    assert mgr.try_set_busy("thread-1") is True
    assert mgr.try_set_busy("thread-1") is False

    # Different thread is independent
    assert mgr.try_set_busy("thread-2") is True

    mgr.clear_busy("thread-1")
    assert mgr.try_set_busy("thread-1") is True


async def test_connection_manager_busy_resets_on_reconnect():
    mgr = ConnectionManager()
    ws = _make_ws()
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    mgr.try_set_busy("thread-1")
    assert mgr.try_set_busy("thread-1") is False

    await mgr.connect(ws, store)

    # Busy flag should be reset
    assert mgr.try_set_busy("thread-1") is True


async def test_message_to_dict_serializes_correctly():
    msg_id = uuid4()
    now = datetime.now(timezone.utc)
    msg = Message(
        id=msg_id,
        role="user",
        text="test",
        components=[],
        read=True,
        created_at=now,
        thread_id="t1",
    )

    d = message_to_dict(msg)

    assert d["id"] == str(msg_id)
    assert d["role"] == "user"
    assert d["text"] == "test"
    assert d["read"] is True
    assert d["thread_id"] == "t1"
    assert d["created_at"] == now.isoformat()


async def test_connection_manager_push_clears_ws_on_send_error():
    mgr = ConnectionManager()
    ws = _make_ws()
    ws.send_json = AsyncMock(side_effect=Exception("broken pipe"))

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])
    await mgr.connect(ws, store)
    ws.send_json.reset_mock()
    ws.send_json.side_effect = Exception("broken pipe")

    msg = _make_message()
    await mgr.push(msg)

    assert not mgr.connected


# ── Confirmation persistence and replay ───────────────────────────────────────


async def test_connect_replays_all_pending_confirmations():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    confirmation_store = AsyncMock()
    confirmation_store.get_all_pending = AsyncMock(
        return_value=[
            {
                "thread_id": "t1",
                "request_id": "req-123",
                "prompt": "Delete 50 emails?",
                "actions": [{"label": "Approve", "payload": "yes"}],
            },
            {
                "thread_id": "t2",
                "request_id": "req-456",
                "prompt": "Send newsletter?",
                "actions": [{"label": "Approve", "payload": "yes"}],
            },
        ]
    )

    await mgr.connect(ws, store, confirmation_store)

    frames = [call[0][0] for call in ws.send_json.call_args_list]
    confirm_frames = [f for f in frames if f.get("type") == "confirm_request"]
    assert len(confirm_frames) == 2
    assert confirm_frames[0]["id"] == "req-123"
    assert confirm_frames[0]["thread_id"] == "t1"
    assert confirm_frames[1]["id"] == "req-456"
    assert confirm_frames[1]["thread_id"] == "t2"


async def test_connect_no_replay_when_no_pending_confirmation():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    confirmation_store = AsyncMock()
    confirmation_store.get_all_pending = AsyncMock(return_value=[])

    await mgr.connect(ws, store, confirmation_store)

    frames = [call[0][0] for call in ws.send_json.call_args_list]
    confirm_frames = [f for f in frames if f.get("type") == "confirm_request"]
    assert len(confirm_frames) == 0


async def test_connect_handles_confirmation_store_error_gracefully():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    confirmation_store = AsyncMock()
    confirmation_store.get_all_pending = AsyncMock(side_effect=RuntimeError("db down"))

    # Should not raise
    await mgr.connect(ws, store, confirmation_store)
    assert mgr.connected


async def test_connect_works_without_confirmation_store():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    # confirmation_store=None (default) must not raise
    await mgr.connect(ws, store, confirmation_store=None)
    assert mgr.connected


async def test_send_frame_injects_thread_id():
    mgr = ConnectionManager()
    ws = _make_ws()
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])
    await mgr.connect(ws, store)
    ws.send_json.reset_mock()

    await mgr.send_frame({"type": "typing"}, "thread-abc")

    frame = ws.send_json.call_args[0][0]
    assert frame["thread_id"] == "thread-abc"
    assert frame["type"] == "typing"


async def test_send_onboarding_view_includes_session_metadata():
    mgr = ConnectionManager()
    ws = _make_ws()
    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])
    await mgr.connect(ws, store)
    ws.send_json.reset_mock()
    session_id = uuid4()

    await send_onboarding_view(
        mgr,
        OnboardingView(
            session_id=session_id,
            text="Setup",
            components=[{"type": "card", "body": "Hello"}],
        ),
    )

    frame = ws.send_json.call_args[0][0]
    assert frame["type"] == "message"
    assert frame["message"]["components"][0]["type"] == "card"
    assert frame["message"]["id"]
    assert frame["message"]["created_at"]
    assert frame["onboarding"]["session_id"] == str(session_id)
    assert frame["onboarding"]["completed"] is False


async def test_component_submit_uses_onboarding_coordinator():
    mgr = ConnectionManager()
    ws = _make_ws()
    msg_store = AsyncMock()
    session_id = uuid4()
    view = OnboardingView(session_id=session_id, text="Next", components=[])

    container = AsyncMock()
    container.onboarding_coordinator.submit = AsyncMock(return_value=view)

    with patch(
        "ze_api.api.websocket.component_submit.send_onboarding_view", new=AsyncMock()
    ) as mock_send_view:
        await handle_component_submit(
            ws,
            {
                "session_id": str(session_id),
                "step_id": "profile.name",
                "values": {"name": "Ada"},
            },
            container,
            mgr,
            msg_store,
            None,
        )

    container.onboarding_coordinator.submit.assert_awaited_once_with(
        session_id=session_id,
        step_id="profile.name",
        values={"name": "Ada"},
    )
    mock_send_view.assert_awaited_once_with(mgr, view)


async def test_component_submit_falls_back_to_graph_on_unknown_session():
    mgr = ConnectionManager()
    ws = _make_ws()
    msg_store = AsyncMock()

    container = AsyncMock()
    container.onboarding_coordinator.submit = AsyncMock(
        side_effect=OnboardingError("Unknown onboarding step"),
    )

    with patch(
        "ze_api.api.websocket.component_submit.handle_message",
        new=AsyncMock(return_value=None),
    ) as mock_handle:
        await handle_component_submit(
            ws,
            {
                "session_id": str(uuid4()),
                "step_id": "agent.form",
                "values": {"field": "value"},
                "thread_id": "thread-1",
            },
            container,
            mgr,
            msg_store,
            None,
        )

    mock_handle.assert_awaited_once()
    message_data = mock_handle.call_args[0][1]
    assert message_data["thread_id"] == "thread-1"
    assert "[component_submit:agent.form]" in message_data["text"]
    assert '"field": "value"' in message_data["text"]
