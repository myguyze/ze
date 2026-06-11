from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_api.api.ws import ConnectionManager, _message_to_dict
from ze_core.messages.types import Message


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


async def test_connection_manager_busy_flag():
    mgr = ConnectionManager()

    assert mgr.try_set_busy() is True
    assert mgr.try_set_busy() is False

    mgr.clear_busy()
    assert mgr.try_set_busy() is True


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

    d = _message_to_dict(msg)

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

async def test_connect_replays_pending_confirmation():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    confirmation_store = AsyncMock()
    confirmation_store.get_any_pending = AsyncMock(return_value={
        "thread_id": "t1",
        "request_id": "req-123",
        "prompt": "Delete 50 emails?",
        "actions": [{"label": "Approve", "payload": "yes"}],
    })

    await mgr.connect(ws, store, confirmation_store)

    frames = [call[0][0] for call in ws.send_json.call_args_list]
    confirm_frames = [f for f in frames if f.get("type") == "confirm_request"]
    assert len(confirm_frames) == 1
    assert confirm_frames[0]["id"] == "req-123"
    assert confirm_frames[0]["prompt"] == "Delete 50 emails?"


async def test_connect_no_replay_when_no_pending_confirmation():
    mgr = ConnectionManager()
    ws = _make_ws()

    store = AsyncMock()
    store.list_unread = AsyncMock(return_value=[])

    confirmation_store = AsyncMock()
    confirmation_store.get_any_pending = AsyncMock(return_value=None)

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
    confirmation_store.get_any_pending = AsyncMock(side_effect=RuntimeError("db down"))

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
