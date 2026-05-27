from __future__ import annotations

from typing import TYPE_CHECKING

from ze.logging import get_logger
from ze_core.interface.types import Notification

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup
    from ze.interface.telegram import TelegramInterface

log = get_logger(__name__)

_MAX_MESSAGE_LEN = 4096


class ProactiveNotifier:
    """Delivers proactive messages through TelegramInterface."""

    def __init__(self, interface: TelegramInterface) -> None:
        self._interface = interface
        self._log = get_logger(__name__)

    async def push(self, text: str, parse_mode: str | None = None) -> None:
        fmt = "markdown" if parse_mode == "HTML" else "text"
        try:
            for chunk in _split(text):
                await self._interface.push(Notification(content=chunk, format=fmt))
        except Exception as exc:
            self._log.warning("proactive_push_failed", error=str(exc))

    async def push_with_keyboard(
        self,
        text: str,
        reply_markup: InlineKeyboardMarkup,
        parse_mode: str | None = None,
    ) -> None:
        try:
            await self._interface.push_with_keyboard(
                text,
                reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as exc:
            self._log.warning("proactive_push_failed", error=str(exc))


def _split(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
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
