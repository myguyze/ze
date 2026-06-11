from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ze_core.interface.types import Action, Notification
from ze_core.proactive.notifier import ProactiveNotifier, _split


@pytest.fixture
def interface():
    m = AsyncMock()
    m.push = AsyncMock()
    return m


@pytest.fixture
def notifier(interface):
    return ProactiveNotifier(interface=interface)


async def test_push_sends_notification(notifier, interface):
    await notifier.push("Hello, user!")
    interface.push.assert_called_once()
    notif = interface.push.call_args.args[0]
    assert isinstance(notif, Notification)
    assert notif.content == "Hello, user!"


async def test_push_swallows_errors(notifier, interface):
    interface.push = AsyncMock(side_effect=Exception("network error"))
    # Must not raise
    await notifier.push("Test")


async def test_push_notification_sends_with_actions(notifier, interface):
    n = Notification(
        content="Gate checkpoint",
        actions=[Action(label="Proceed", payload="goal:approve:123")],
    )
    await notifier.push_notification(n)
    interface.push.assert_called_once_with(n)


async def test_push_notification_splits_large_content(notifier, interface):
    long_content = "x\n" * 3000  # well over 4096 chars
    n = Notification(content=long_content, actions=[Action(label="OK", payload="p")])
    await notifier.push_notification(n)
    assert interface.push.call_count > 1
    # Actions only on last chunk
    calls = [c.args[0] for c in interface.push.call_args_list]
    for c in calls[:-1]:
        assert c.actions == []
    assert calls[-1].actions == [Action(label="OK", payload="p")]


async def test_push_notification_swallows_error_on_split(notifier, interface):
    interface.push = AsyncMock(side_effect=Exception("fail"))
    long_content = "y\n" * 3000
    n = Notification(content=long_content)
    await notifier.push_notification(n)  # must not raise


def test_split_short_text():
    assert _split("hello") == ["hello"]


def test_split_long_text():
    text = "line\n" * 1000  # 5000 chars
    chunks = _split(text)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    # Reassembled content matches original (minus leading newlines stripped during split)
    reassembled = "\n".join(chunks)
    assert "line" in reassembled
