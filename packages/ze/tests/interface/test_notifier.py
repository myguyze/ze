from unittest.mock import AsyncMock, MagicMock

from ze.interface.telegram import TelegramInterface
from ze_core.proactive.notifier import ProactiveNotifier, _split
from ze_core.interface.types import Action, Notification


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


async def test_notifier_push_notification_with_actions():
    interface = make_interface()
    n = ProactiveNotifier(interface=interface)
    await n.push_notification(
        Notification(
            content="Pick one",
            format="html",
            actions=[Action(label="Yes", payload="yes:1")],
        )
    )
    interface._bot.send_message.assert_awaited_once()
    call_kwargs = interface._bot.send_message.call_args.kwargs
    assert call_kwargs.get("reply_markup") is not None


def test_split_short_message():
    assert _split("hello") == ["hello"]
