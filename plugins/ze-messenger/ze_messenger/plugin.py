from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ze_agents.client import LLMClient
from ze_agents.settings import Settings
from ze_logging import get_logger
from ze_memory.store import MemoryStore
from ze_personal.channels.thread_channel_map import ThreadChannelMap
from ze_personal.channels.user_channel_store import UserChannelStore
from ze_personal.channels.watermark_store import ChannelWatermarkStore
from ze_personal.contacts.channel_store import ContactChannelStore
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.scheduler import ProactiveScheduler
from ze_sdk import ZePlugin

if TYPE_CHECKING:
    from ze_google.auth import GoogleCredentials

log = get_logger(__name__)


class MessengerPlugin(ZePlugin):
    """Registers the messenger agent and inbound polling pipeline."""

    def __init__(
        self,
        *,
        memory_store: MemoryStore,
        contact_channel_store: ContactChannelStore,
        user_channel_store: UserChannelStore,
        watermark_store: ChannelWatermarkStore,
        thread_channel_map: ThreadChannelMap,
        notifier: ProactiveNotifier,
        openrouter_client: LLMClient,
        settings: Settings,
        google_credentials: GoogleCredentials | None = None,
        embedder: Any = None,
        public_url: str = "",
    ) -> None:
        self._google_credentials = google_credentials
        self._public_url = public_url or ""
        self._memory_store = memory_store
        self._contact_channel_store = contact_channel_store
        self._user_channel_store = user_channel_store
        self._watermark_store = watermark_store
        self._thread_channel_map = thread_channel_map
        self._notifier = notifier
        self._llm_client = openrouter_client
        self._settings = settings
        self._embedder = embedder

        from ze_messenger.signals import MessagingSignalSource
        self._signal_source = MessagingSignalSource()
        self._polling_job: Any = None
        self._gmail_channel: Any = None

    def channels(self) -> list:
        if self._google_credentials is None:
            return []
        import os
        from ze_google.gmail_channel import GmailChannel
        public_url = self._public_url or os.environ.get("PUBLIC_URL", "") or None
        self._gmail_channel = GmailChannel(credentials=self._google_credentials, public_url=public_url)
        return [self._gmail_channel]

    def memory_policies(self) -> dict:
        from ze_memory.policies import EmailPolicy
        return {"email": EmailPolicy()}

    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]

    def signal_sources(self) -> list:
        return [self._signal_source]

    def agent_deps(self, accumulated: dict) -> dict:
        from ze_communication.registry import ChannelRegistry
        from ze_personal.channels.user_channel_store import UserChannelStore
        from ze_personal.channels.thread_channel_map import ThreadChannelMap

        deps: dict = {
            UserChannelStore: self._user_channel_store,
            ThreadChannelMap: self._thread_channel_map,
        }
        if ChannelRegistry in accumulated:
            deps[ChannelRegistry] = accumulated[ChannelRegistry]
        return deps

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_messenger.agents.messenger.tools",
            "ze_messenger.agents.messenger.agent",
        ]

    async def startup(self, container: Any) -> None:
        from ze_messenger.inbound.processor import InboundMessageProcessor
        from ze_messenger.jobs.inbound_poll import InboundPollingJob

        automated_patterns: list[str] = (
            self._settings.config.get("messaging", {}).get("automated_senders", [])
        )

        processor = InboundMessageProcessor(
            memory_store=self._memory_store,
            contact_channel_store=self._contact_channel_store,
            thread_channel_map=self._thread_channel_map,
            notifier=self._notifier,
            signal_source=self._signal_source,
            embedder=self._embedder,
            automated_sender_patterns=automated_patterns,
            llm_client=self._llm_client,
        )

        # Expose processor on container so WebhookDispatcher._trigger_messenger can use it.
        container._webhook_processor = processor

        channel_registry = getattr(container, "channel_registry", None)
        if channel_registry is not None:
            self._polling_job = InboundPollingJob(
                registry=channel_registry,
                watermark_store=self._watermark_store,
                user_channel_store=self._user_channel_store,
                processor=processor,
            )
            log.info("inbound_polling_job_created")
        else:
            log.warning("channel_registry_not_available_for_polling_job")

    def register_proactive_jobs(
        self,
        scheduler: ProactiveScheduler,
        settings: Settings,
        *,
        consolidation_enabled: bool = True,
    ) -> None:
        import os

        if self._polling_job is not None:
            proactive_cfg = settings.config.get("proactive", {})
            poll_seconds = proactive_cfg.get("inbound_poll_interval_seconds", 300)
            poll_minutes = max(1, poll_seconds // 60)
            cron = f"*/{poll_minutes} * * * *"
            scheduler.register(self._polling_job, cron=cron)
            log.info("inbound_poll_scheduled", cron=cron)

        if self._gmail_channel is not None and self._gmail_channel.supports_push:
            from ze_api.settings import get_settings as get_api_settings
            from ze_messenger.jobs.gmail_watch_renewal import GmailWatchRenewalJob
            topic = get_api_settings().gmail_pubsub_topic or os.environ.get("GMAIL_PUBSUB_TOPIC", "")
            if topic:
                renewal_job = GmailWatchRenewalJob(channel=self._gmail_channel, topic_name=topic)
                scheduler.register(renewal_job, cron="0 0 * * 0")  # weekly on Sunday midnight
                log.info("gmail_watch_renewal_scheduled")
