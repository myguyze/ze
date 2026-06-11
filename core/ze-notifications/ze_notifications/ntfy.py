from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass

import aiohttp

from ze_notifications.types import Notification

log = logging.getLogger(__name__)


@dataclass
class NtfyConfig:
    base_url: str   # "https://ntfy.sh" or self-hosted URL (no trailing slash)
    topic: str      # e.g. "ze-joao-abc123" — keep non-guessable for ntfy.sh
    token: str | None = None  # Bearer token; required when base_url contains "ntfy.sh"


class NtfyNotifier:
    def __init__(self, config: NtfyConfig, session: aiohttp.ClientSession) -> None:
        if "ntfy.sh" in config.base_url and not config.token:
            raise ValueError(
                "NTFY_TOKEN is required for ntfy.sh topics. "
                "Set token in config or switch to a self-hosted ntfy instance."
            )
        self._config = config
        self._session = session
        self._url = f"{config.base_url}/{config.topic}"

    async def push(self, notification: Notification) -> None:
        headers = self._build_headers(notification)
        try:
            async with self._session.post(
                self._url,
                data=notification.body.encode(),
                headers=headers,
            ) as resp:
                if resp.status >= 400:
                    log.warning(
                        "ntfy push failed: status=%s topic=%s",
                        resp.status,
                        self._config.topic,
                    )
        except Exception as exc:
            log.warning("ntfy push error: %s", exc)

    def _build_headers(self, n: Notification) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Title": n.title,
            "X-Priority": str(n.priority),
        }
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"
        if n.tags:
            headers["X-Tags"] = ",".join(n.tags)
        if n.data:
            headers["X-Click"] = _encode_deep_link(n.data)
        return headers


def _encode_deep_link(data: dict[str, str]) -> str:
    return "ze://navigate?" + urllib.parse.urlencode(data)
