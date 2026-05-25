from unittest.mock import AsyncMock, MagicMock

from ze.proactive.notifier import ProactiveNotifier, _split


def make_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


async def test_notifier_push_sends_message():
    bot = make_bot()
    n = ProactiveNotifier(bot=bot, chat_id=123)
    await n.push("Hello!")
    bot.send_message.assert_awaited_once_with(123, "Hello!", parse_mode=None)


async def test_notifier_push_uses_correct_chat_id():
    bot = make_bot()
    n = ProactiveNotifier(bot=bot, chat_id=9999)
    await n.push("Hi")
    call_args = bot.send_message.call_args[0]
    assert call_args[0] == 9999


async def test_notifier_push_swallows_error():
    bot = make_bot()
    bot.send_message = AsyncMock(side_effect=Exception("Telegram down"))
    n = ProactiveNotifier(bot=bot, chat_id=1)
    await n.push("test")  # must not raise


async def test_notifier_push_splits_long_message():
    bot = make_bot()
    n = ProactiveNotifier(bot=bot, chat_id=1)
    # Build a message longer than 4096 chars with a newline boundary
    line = "x" * 100
    long_text = "\n".join([line] * 50)  # 5050 chars with newlines
    await n.push(long_text)
    assert bot.send_message.await_count >= 2


def test_split_short_message():
    result = _split("hello")
    assert result == ["hello"]


def test_split_long_message_at_newline():
    limit = 20
    text = "a" * 10 + "\n" + "b" * 15
    result = _split(text, limit=limit)
    assert len(result) == 2
    assert result[0] == "a" * 10
    assert result[1] == "b" * 15
