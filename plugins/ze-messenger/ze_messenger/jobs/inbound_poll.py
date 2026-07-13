from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ze_logging import get_logger
from ze_personal.channels.types import UserChannel

_log = get_logger(__name__)


class InboundPollingJob:
    job_id = "inbound_poll"

    def __init__(
        self,
        registry: object,  # ChannelRegistry — avoid circular at import time
        watermark_store: object,  # ChannelWatermarkStore
        user_channel_store: object,  # UserChannelStore
        processor: object,  # InboundMessageProcessor
    ) -> None:
        self._registry = registry
        self._watermarks = watermark_store
        self._user_channels = user_channel_store
        self._processor = processor

    async def run(self) -> None:
        all_user_channels = await self._user_channels.list_all()
        registered = {uc.channel_id for uc in all_user_channels}
        enabled = {uc.channel_id for uc in all_user_channels if uc.poll_enabled}

        for channel in self._registry.inbound_channels():
            # Skip channels that are registered but explicitly disabled
            if channel.channel_id in registered and channel.channel_id not in enabled:
                continue
            if channel.supports_push:
                continue  # Phase 86 handles these via webhook
            await self._poll(channel)

    async def _poll(self, channel: object) -> None:
        try:
            if hasattr(channel, "_resolve_user_email"):
                await channel._resolve_user_email()
            since = await self._watermarks.get(channel.channel_id)
            messages = await channel.poll_new_messages(since=since)
        except Exception as exc:
            _log.warning(
                "inbound_poll_failed",
                channel_id=channel.channel_id,
                error=str(exc),
            )
            return

        if not messages:
            await self._watermarks.set(channel.channel_id, datetime.now(timezone.utc))
            return

        for msg in messages:
            try:
                await self._processor.process(msg, channel_id=channel.channel_id)
            except Exception:
                _log.warning(
                    "inbound_message_process_failed",
                    channel_id=channel.channel_id,
                    message_id=getattr(msg, "message_id", "?"),
                )

        await self._watermarks.set(channel.channel_id, datetime.now(timezone.utc))

        # Auto-register channel in user_channels on first successful poll
        handle = getattr(channel, "_user_email", None) or channel.channel_id
        await self._user_channels.upsert(
            UserChannel(
                id=uuid4(),
                channel_id=channel.channel_id,
                channel_type=channel.channel_type.value,
                handle=handle,
                display_name=None,
                is_default_outbound=False,
                poll_enabled=True,
                created_at=datetime.now(timezone.utc),
            )
        )
