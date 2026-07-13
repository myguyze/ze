from __future__ import annotations

from typing import TYPE_CHECKING

from ze_logging import get_logger

if TYPE_CHECKING:
    from ze_google.gmail_channel import GmailChannel

log = get_logger(__name__)


class GmailWatchRenewalJob:
    """Renews Gmail inbox watch weekly. Gmail watch expires after 7 days."""

    job_id = "gmail_watch_renewal"

    def __init__(self, channel: GmailChannel, topic_name: str) -> None:
        self._channel = channel
        self._topic_name = topic_name

    async def run(self) -> None:
        if not self._channel.supports_push:
            return
        try:
            await self._channel.register_push(self._topic_name)
            log.info("gmail_watch_renewed", topic=self._topic_name)
        except Exception as exc:
            log.error(
                "gmail_watch_renewal_failed", topic=self._topic_name, error=str(exc)
            )
