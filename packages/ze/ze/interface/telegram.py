from __future__ import annotations

import html as _html
from typing import ClassVar, Literal

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from ze.logging import get_logger
from ze.telegram.formatting import md_to_html, split_html
from ze.telegram.keyboards import confirmation_keyboard
from ze_core.interface.types import (
    ConfirmationRequest,
    Notification,
    OutboundMessage,
)

log = get_logger(__name__)


class TelegramInterface:
    """Ze's AppInterface adapter for Telegram (async confirmation style)."""

    confirmation_style: ClassVar[Literal["inline", "async"]] = "async"

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._default_chat_id = chat_id
        self._active_chat_id: int | None = None

    def set_chat(self, chat_id: int) -> None:
        """Bind the chat for the current turn (session_id == str(chat_id))."""
        self._active_chat_id = chat_id

    def _chat_id(self) -> int:
        return self._active_chat_id if self._active_chat_id is not None else self._default_chat_id

    async def send(self, message: OutboundMessage) -> None:
        try:
            if message.format == "markdown":
                html = md_to_html(message.content)
            else:
                html = _html.escape(message.content)
            for chunk in split_html(html):
                await self._bot.send_message(self._chat_id(), chunk, parse_mode="HTML")
        except Exception as exc:
            log.warning("interface_send_failed", chat_id=self._chat_id(), error=str(exc))

    async def send_confirmation(
        self,
        request: ConfirmationRequest,
        *,
        agent: str = "",
        action: str = "",
    ) -> None:
        draft = request.content or ""
        text = (
            f"⚠️ <b>Confirmation required</b>\n\n"
            f"<b>Agent:</b> {_html.escape(agent)}\n"
            f"<b>Action:</b> {_html.escape(action)}\n\n"
            f"<b>Draft:</b>\n{md_to_html(draft)}"
        )
        try:
            await self._bot.send_message(
                self._chat_id(),
                text,
                parse_mode="HTML",
                reply_markup=confirmation_keyboard(),
            )
        except Exception as exc:
            log.warning(
                "interface_send_confirmation_failed",
                chat_id=self._chat_id(),
                error=str(exc),
            )

    async def push(self, notification: Notification) -> None:
        try:
            parse_mode = "HTML" if notification.format == "markdown" else None
            prefix = "[!] " if notification.urgency == "high" else ""
            content = prefix + notification.content
            if notification.format == "markdown":
                body = md_to_html(content)
                parse_mode = "HTML"
            else:
                body = content
            for chunk in split_html(body) if parse_mode == "HTML" else _split_plain(body):
                await self._bot.send_message(self._chat_id(), chunk, parse_mode=parse_mode)
        except Exception as exc:
            log.warning("interface_push_failed", chat_id=self._chat_id(), error=str(exc))

    async def push_with_keyboard(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup,
        *,
        parse_mode: str | None = None,
    ) -> None:
        """Telegram-specific proactive helper (not part of AppInterface)."""
        try:
            await self._bot.send_message(
                self._chat_id(),
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as exc:
            log.warning("interface_push_keyboard_failed", chat_id=self._chat_id(), error=str(exc))


def _split_plain(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
