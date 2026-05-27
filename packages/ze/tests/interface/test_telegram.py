from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.interface.telegram import TelegramInterface
from ze_core.interface.types import ConfirmationRequest, Notification, OutboundMessage


@pytest.fixture
def bot():
    b = MagicMock()
    b.send_message = AsyncMock()
    return b


@pytest.fixture
def iface(bot):
    return TelegramInterface(bot=bot, chat_id=42)


class TestTelegramInterface:
    async def test_send_markdown(self, iface, bot):
        iface.set_chat(99)
        await iface.send(OutboundMessage(content="**hi**", format="markdown"))
        bot.send_message.assert_awaited()
        assert bot.send_message.call_args[0][0] == 99

    async def test_send_confirmation(self, iface, bot):
        iface.set_chat(7)
        await iface.send_confirmation(
            ConfirmationRequest(content="draft body", options=["Yes", "No"]),
            agent="calendar",
            action="create",
        )
        bot.send_message.assert_awaited_once()
        text = bot.send_message.call_args[0][1]
        assert "calendar" in text
        assert "create" in text

    async def test_push_swallows_errors(self, iface, bot):
        bot.send_message = AsyncMock(side_effect=RuntimeError("down"))
        await iface.push(Notification(content="alert"))

    def test_confirmation_style_is_async(self, iface):
        assert iface.confirmation_style == "async"
