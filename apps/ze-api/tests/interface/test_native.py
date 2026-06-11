from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_core.interface.types import Notification, OutboundMessage
from ze_api.interface.native import NativeAppInterface


def _make_interface(
    store=None,
    conn=None,
    notifier=None,
):
    store = store or AsyncMock()
    conn = conn or AsyncMock()
    conn.push = AsyncMock()
    conn.send_frame = AsyncMock()
    notifier = notifier or AsyncMock()
    return NativeAppInterface(
        message_store=store,
        connection_manager=conn,
        notifier=notifier,
    ), store, conn, notifier


async def test_send_message_saves_and_pushes_and_notifies():
    iface, store, conn, notifier = _make_interface()

    await iface.send(OutboundMessage(content="Hello world", format="text"))

    store.save.assert_called_once()
    saved_msg = store.save.call_args[0][0]
    assert saved_msg.role == "assistant"
    assert saved_msg.text == "Hello world"
    assert saved_msg.read is False

    conn.push.assert_called_once()
    notifier.push.assert_called_once()
    ntfy_notif = notifier.push.call_args[0][0]
    assert ntfy_notif.title == "Ze"
    assert ntfy_notif.body == "Hello world"


async def test_send_message_continues_if_ws_disconnected():
    conn = MagicMock()
    conn.push = AsyncMock(side_effect=Exception("disconnected"))
    conn.send_frame = AsyncMock()
    iface, store, _, notifier = _make_interface(conn=conn)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    notifier.push.assert_called_once()


async def test_send_message_continues_if_ntfy_raises():
    notifier = AsyncMock()
    notifier.push = AsyncMock(side_effect=Exception("ntfy down"))
    iface, store, conn, _ = _make_interface(notifier=notifier)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    conn.push.assert_called_once()


async def test_push_notification_uses_correct_priority():
    iface, store, conn, notifier = _make_interface()

    await iface.push(Notification(content="Alert!", urgency="high"))

    ntfy_notif = notifier.push.call_args[0][0]
    assert ntfy_notif.priority == 5


async def test_send_truncates_ntfy_body_to_200_chars():
    iface, store, conn, notifier = _make_interface()
    long_text = "x" * 500

    await iface.send(OutboundMessage(content=long_text))

    ntfy_notif = notifier.push.call_args[0][0]
    assert len(ntfy_notif.body) == 200


async def test_no_ntfy_when_notifier_is_none():
    iface, store, conn, _ = _make_interface(notifier=None)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    conn.push.assert_called_once()
