from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


from ze_agents.interface.types import Notification, OutboundMessage
from ze_api.interface.native import NativeAppInterface


def _make_conn(*, connected: bool = False) -> MagicMock:
    conn = MagicMock()
    conn.push = AsyncMock()
    conn.send_frame = AsyncMock()
    conn.connected = connected
    return conn


def _make_interface(
    store=None,
    conn=None,
    notifier=None,
    *,
    connected: bool = False,
):
    store = store or AsyncMock()
    conn = conn or _make_conn(connected=connected)
    notifier = notifier or AsyncMock()
    return NativeAppInterface(
        message_store=store,
        connection_manager=conn,
        notifier=notifier,
    ), store, conn, notifier


async def test_send_message_saves_and_pushes():
    iface, store, conn, notifier = _make_interface(connected=False)

    await iface.send(OutboundMessage(content="Hello world", format="text"))

    store.save.assert_called_once()
    saved_msg = store.save.call_args[0][0]
    assert saved_msg.role == "assistant"
    assert saved_msg.text == "Hello world"
    assert saved_msg.read is False

    conn.push.assert_called_once()


async def test_ntfy_fires_when_disconnected():
    iface, store, conn, notifier = _make_interface(connected=False)

    await iface.send(OutboundMessage(content="Hello world", format="text"))

    notifier.push.assert_called_once()
    ntfy_notif = notifier.push.call_args[0][0]
    assert ntfy_notif.title == "Ze"
    assert ntfy_notif.body == "Hello world"


async def test_ntfy_suppressed_when_connected():
    iface, store, conn, notifier = _make_interface(connected=True)

    await iface.send(OutboundMessage(content="Hello world"))

    conn.push.assert_called_once()
    notifier.push.assert_not_called()


async def test_send_message_continues_if_ws_disconnected():
    conn = _make_conn(connected=False)
    conn.push = AsyncMock(side_effect=Exception("disconnected"))
    iface, store, _, notifier = _make_interface(conn=conn)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    notifier.push.assert_called_once()


async def test_send_message_continues_if_ntfy_raises():
    notifier = AsyncMock()
    notifier.push = AsyncMock(side_effect=Exception("ntfy down"))
    iface, store, conn, _ = _make_interface(notifier=notifier, connected=False)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    conn.push.assert_called_once()


async def test_push_notification_uses_correct_priority():
    iface, store, conn, notifier = _make_interface(connected=False)

    await iface.push(Notification(content="Alert!", urgency="high"))

    ntfy_notif = notifier.push.call_args[0][0]
    assert ntfy_notif.priority == 5


async def test_send_truncates_ntfy_body_to_200_chars():
    iface, store, conn, notifier = _make_interface(connected=False)
    long_text = "x" * 500

    await iface.send(OutboundMessage(content=long_text))

    ntfy_notif = notifier.push.call_args[0][0]
    assert len(ntfy_notif.body) == 200


async def test_no_ntfy_when_notifier_is_none():
    iface, store, conn, _ = _make_interface(notifier=None, connected=False)

    # Should not raise
    await iface.send(OutboundMessage(content="Hi"))

    store.save.assert_called_once()
    conn.push.assert_called_once()


async def test_push_with_actions_sends_confirm_request():
    from ze_agents.interface.types import Action, Notification

    iface, store, conn, notifier = _make_interface(connected=False)
    await iface.push(Notification(
        content="<b>Goal</b> — proposed plan",
        format="html",
        urgency="high",
        actions=[
            Action(label="Start goal", payload="goal_plan:yes:abc"),
            Action(label="Cancel", payload="goal_plan:no:abc"),
        ],
    ))

    store.save.assert_called_once()
    conn.push.assert_called_once()
    conn.send_frame.assert_called_once()
    frame = conn.send_frame.call_args[0][0]
    assert frame["type"] == "confirm_request"
    assert frame["actions"][0]["value"] == "goal_plan:yes:abc"
    assert frame["actions"][1]["style"] == "danger"
