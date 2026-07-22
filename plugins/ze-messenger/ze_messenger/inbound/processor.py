from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from ze_communication.types import ChannelType, InboundMessage
from ze_logging import get_logger
from ze_memory.store import MemoryStore

if TYPE_CHECKING:
    from ze_agents.client import LLMClient
    from ze_personal.channels.thread_channel_map import ThreadChannelMap
    from ze_personal.contacts.channel_store import ContactChannelStore
    from ze_proactive.notifier import ProactiveNotifier
    from ze_messenger.signals import MessagingSignalSource


_AUTOMATED_PREFIXES = (
    "noreply@",
    "no-reply@",
    "notifications@",
    "postmaster@",
    "mailer-daemon@",
    "donotreply@",
    "bounce@",
    "daemon@",
    "automated@",
)

log = get_logger(__name__)


class SenderClass(StrEnum):
    KNOWN_CONTACT = "known_contact"
    REPLIED_TO = "replied_to"
    UNKNOWN_HUMAN = "unknown_human"
    AUTOMATED = "automated"


def _is_automated(
    sender: str,
    headers: dict[str, str],
    extra_patterns: list[str],
) -> bool:
    addr = sender.lower()
    # Strip display name — get just the email address
    m = re.search(r"<([^>]+)>", addr)
    if m:
        addr = m.group(1)

    for prefix in _AUTOMATED_PREFIXES:
        if addr.startswith(prefix):
            return True

    precedence = headers.get("Precedence", "").lower()
    if precedence in ("bulk", "list", "junk"):
        return True

    if "List-Unsubscribe" in headers:
        return True

    for pattern in extra_patterns:
        try:
            if re.search(pattern, addr, re.IGNORECASE):
                return True
        except re.error:
            pass

    return False


class InboundMessageProcessor:
    """Processes a single inbound message through the Ze pipeline."""

    def __init__(
        self,
        memory_store: MemoryStore,
        contact_channel_store: ContactChannelStore,
        thread_channel_map: ThreadChannelMap,
        notifier: ProactiveNotifier,
        signal_source: MessagingSignalSource,
        embedder: Any,
        automated_sender_patterns: list[str],
        llm_client: LLMClient | None = None,
    ) -> None:
        self._memory = memory_store
        self._contacts = contact_channel_store
        self._thread_map = thread_channel_map
        self._notifier = notifier
        self._signals = signal_source
        self._embedder = embedder
        self._automated_patterns = automated_sender_patterns
        self._llm_client = llm_client
        # Optional hook wired post-construction by ze-api (open-loop extraction,
        # FR-008's email/messenger inflow) — kept generic here so ze-messenger has
        # no dependency on ze-worldstate (plan.md: ze-api is the only wiring point).
        self.loop_extractor: Callable[[str, str], Awaitable[None]] | None = None

    async def process(self, msg: InboundMessage, channel_id: str) -> SenderClass:
        sender_class = await self._classify(msg)

        if sender_class == SenderClass.AUTOMATED:
            return sender_class

        if msg.thread_id:
            await self._thread_map.set(msg.thread_id, channel_id)

        prompt = f"[Inbound {msg.channel_type} from {msg.sender}]" + (
            f" Subject: {msg.subject}" if msg.subject else ""
        )
        embedding = (
            self._embedder.encode(f"{prompt} {msg.body[:500]}")
            if self._embedder
            else None
        )

        await self._memory.write_episode(
            session_id=msg.message_id,
            agent="messenger",
            prompt=prompt,
            response=msg.body,
            embedding=embedding,
        )

        significant = sender_class in (
            SenderClass.KNOWN_CONTACT,
            SenderClass.REPLIED_TO,
        )

        if significant:
            self._signals.push(msg)

            known = await self._contacts.find_by_handle(
                channel_type=ChannelType(msg.channel_type),
                handle=msg.sender,
            )
            if known:
                subject_part = f": {msg.subject}" if msg.subject else ""
                await self._notifier.push(
                    title=f"Message from {known.name or msg.sender}{subject_part}",
                    body=msg.body[:200],
                    tags=["message", str(msg.channel_type)],
                )

        if significant:
            asyncio.create_task(self._extract_facts(msg))
            if self.loop_extractor is not None:
                asyncio.create_task(self.loop_extractor(msg.body, "email"))

        return sender_class

    async def _classify(self, msg: InboundMessage) -> SenderClass:
        if _is_automated(msg.sender, msg.headers, self._automated_patterns):
            return SenderClass.AUTOMATED
        known = await self._contacts.find_by_handle(
            channel_type=ChannelType(msg.channel_type),
            handle=msg.sender,
        )
        if known:
            return SenderClass.KNOWN_CONTACT
        if msg.thread_id and await self._thread_map.get(msg.thread_id):
            return SenderClass.REPLIED_TO
        return SenderClass.UNKNOWN_HUMAN

    async def _extract_facts(self, msg: InboundMessage) -> None:
        if self._llm_client is None:
            return
        from ze_memory.extractor import extract_facts, fact_extraction_model

        prompt = f"[Inbound {msg.channel_type} from {msg.sender}]" + (
            f" Subject: {msg.subject}" if msg.subject else ""
        )
        try:
            facts = await extract_facts(
                self._llm_client,
                prompt=prompt,
                response=msg.body,
                model=fact_extraction_model(),
            )
            if facts:
                await self._memory.propose_facts(facts)
        except Exception as exc:
            log.warning(
                "inbound_fact_extraction_failed",
                message_id=msg.message_id,
                error=str(exc),
            )
