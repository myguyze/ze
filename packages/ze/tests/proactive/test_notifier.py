from unittest.mock import AsyncMock, MagicMock

from ze.interface.telegram import TelegramInterface
from ze.proactive.notifier import ProactiveNotifier, _split
from ze_core.interface.types import Notification


def make_interface():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return TelegramInterface(bot=bot, chat_id=123)


async def test_notifier_push_sends_message():
    interface = make_interface()
    n = ProactiveNotifier(interface=interface)
    await n.push("Hello!")
    interface._bot.send_message.assert_awaited()


async def test_notifier_push_swallows_error():
    interface = make_interface()
    interface._bot.send_message = AsyncMock(side_effect=Exception("Telegram down"))
    n = ProactiveNotifier(interface=interface)
    await n.push("test")


async def test_notifier_push_splits_long_message():
    interface = make_interface()
    n = ProactiveNotifier(interface=interface)
    line = "x" * 100
    long_text = "\n".join([line] * 50)
    await n.push(long_text)
    assert interface._bot.send_message.await_count >= 2


async def test_notifier_push_with_keyboard():
    interface = make_interface()
    n = ProactiveNotifier(interface=interface)
    markup = MagicMock()
    await n.push_with_keyboard("Pick one", markup, parse_mode="HTML")
    interface._bot.send_message.assert_awaited_once()


def test_split_short_message():
    assert _split("hello") == ["hello"]
