from __future__ import annotations

from typing import Awaitable, Callable

from ze_core.progress.translations import ProgressTranslations


class ProgressReporter:
    """
    Resolves translation keys and delivers localized strings to an injected sink.

    The sink is a channel-specific delivery function (e.g. enqueue for Telegram,
    send for WebSocket). Agents call emit(key) — the reporter handles resolution
    and dispatch. No-op when the key is unknown.
    """

    def __init__(
        self,
        translations: ProgressTranslations,
        sink: Callable[[str], Awaitable[None]],
    ) -> None:
        self._translations = translations
        self._sink = sink

    async def emit(self, key: str, **kwargs: str) -> None:
        text = self._translations.resolve(key, **kwargs)
        if text is not None:
            await self._sink(text)
