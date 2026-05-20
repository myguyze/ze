from aiogram import Bot

from ze.logging import get_logger

_MAX_MESSAGE_LEN = 4096


class ProactiveNotifier:
    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._log = get_logger(__name__)

    async def push(self, text: str) -> None:
        """Send text to the user. Swallows and logs errors — never raises."""
        try:
            for chunk in _split(text):
                await self._bot.send_message(self._chat_id, chunk)
        except Exception as exc:
            self._log.warning("proactive_push_failed", chat_id=self._chat_id, error=str(exc))


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
