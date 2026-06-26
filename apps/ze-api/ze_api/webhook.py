from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import cachetools

from ze_agents.errors import AgentConfigError
from ze_communication.types import ChannelType
from ze_communication.webhook import WebhookPayload
from ze_logging import get_logger

if TYPE_CHECKING:
    from ze_communication.registry import ChannelRegistry
    from ze_plugin.webhook import WebhookHandler

log = get_logger(__name__)


class WebhookSourceNotFoundError(Exception):
    def __init__(self, source: str) -> None:
        super().__init__(f"No webhook handler registered for source {source!r}")
        self.source = source


class WebhookAuthError(Exception):
    def __init__(self, source: str) -> None:
        super().__init__(f"Webhook authentication failed for source {source!r}")
        self.source = source


class EventDeduplicator:
    """In-memory dedup keyed on (source, event_id). TTL 24h, max 10 000 entries."""

    def __init__(self) -> None:
        self._cache: cachetools.TTLCache = cachetools.TTLCache(
            maxsize=10_000, ttl=86_400
        )

    def is_duplicate(self, source: str, event_id: str) -> bool:
        return (source, event_id) in self._cache

    def mark_seen(self, source: str, event_id: str) -> None:
        self._cache[(source, event_id)] = True


def collect_plugin_webhook_handlers(plugins: list) -> dict[str, WebhookHandler]:
    handlers: dict[str, WebhookHandler] = {}
    for plugin in plugins:
        for handler in plugin.webhook_handlers():
            if handler.source_key in handlers:
                raise AgentConfigError(
                    f"Duplicate webhook handler source_key {handler.source_key!r} "
                    f"contributed by {type(plugin).__name__}"
                )
            handlers[handler.source_key] = handler
    return handlers


class WebhookDispatcher:
    def __init__(
        self,
        channel_registry: ChannelRegistry,
        plugin_handlers: dict[str, WebhookHandler],
        container: object,
        deduplicator: EventDeduplicator,
    ) -> None:
        self._channel_registry = channel_registry
        self._plugin_handlers = plugin_handlers
        self._container = container
        self._dedup = deduplicator

    async def dispatch(
        self, source: str, raw_body: bytes, headers: dict[str, str]
    ) -> None:
        payload = WebhookPayload(source=source, raw_body=raw_body, headers=headers)

        # Channel path
        try:
            channel_type = ChannelType(source)
            channel = self._channel_registry.get_inbound(channel_type)
        except ValueError:
            channel = None

        if channel is not None and channel.supports_push:
            verifier = channel.webhook_verifier()
            if verifier is None or not verifier.verify(payload):
                raise WebhookAuthError(source)
            messages = await verifier.parse(payload)
            channel_id = channel.channel_id
            for msg in messages:
                if self._dedup.is_duplicate(source, msg.message_id):
                    log.debug("webhook_duplicate_skipped", source=source, message_id=msg.message_id)
                    continue
                self._dedup.mark_seen(source, msg.message_id)
                asyncio.create_task(self._trigger_messenger(msg, channel_id))
            return

        # Plugin path
        handler = self._plugin_handlers.get(source)
        if handler is not None:
            if not handler.verify(payload):
                raise WebhookAuthError(source)
            asyncio.create_task(handler.handle(payload))
            return

        raise WebhookSourceNotFoundError(source)

    async def _trigger_messenger(self, msg: object, channel_id: str) -> None:
        from ze_communication.types import InboundMessage
        from ze_messenger.inbound.processor import InboundMessageProcessor, SenderClass

        if not isinstance(msg, InboundMessage):
            return

        processor: InboundMessageProcessor | None = getattr(
            self._container, "_webhook_processor", None
        )
        if processor is None:
            log.warning("webhook_no_processor", message_id=msg.message_id)
            return

        try:
            sender_class = await processor.process(msg, channel_id=channel_id)
        except Exception as exc:
            log.error(
                "webhook_processor_failed",
                message_id=msg.message_id,
                error=str(exc),
            )
            return

        if sender_class == SenderClass.AUTOMATED:
            return

        invoke = getattr(self._container, "invoke", None)
        if invoke is None:
            log.warning("webhook_no_invoke", message_id=msg.message_id)
            return

        subject_part = f" Subject: {msg.subject}" if msg.subject else ""
        channel_type = (
            msg.channel_type.value
            if hasattr(msg.channel_type, "value")
            else str(msg.channel_type)
        )
        prompt = (
            f"[Inbound {channel_type} from {msg.sender}{subject_part}]\n"
            f"{msg.body}"
        )
        thread_id = f"inbound:{msg.message_id}"

        try:
            await invoke(prompt, thread_id)
        except Exception as exc:
            log.error(
                "webhook_invoke_failed",
                message_id=msg.message_id,
                error=str(exc),
            )
