from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_communication.types import ChannelType, InboundMessage
from ze_messenger.inbound.processor import InboundMessageProcessor, SenderClass, _is_automated
from ze_messenger.signals import MessagingSignalSource


def _msg(
    sender: str = "alice@example.com",
    subject: str = "Hello",
    body: str = "Hi there",
    thread_id: str | None = "t1",
    headers: dict | None = None,
) -> InboundMessage:
    return InboundMessage(
        message_id="msg1",
        channel_type=ChannelType.EMAIL,
        sender=sender,
        subject=subject,
        body=body,
        thread_id=thread_id,
        received_at=datetime(2026, 6, 26, 10, 0, tzinfo=timezone.utc),
        headers=headers or {},
    )


def _make_processor(
    contact=None,
    thread_channel=None,
    automated_patterns=None,
) -> tuple[InboundMessageProcessor, MagicMock, MagicMock, MessagingSignalSource]:
    memory = AsyncMock()
    contacts = AsyncMock()
    contacts.find_by_handle = AsyncMock(return_value=contact)
    thread_map = AsyncMock()
    thread_map.get = AsyncMock(return_value=thread_channel)
    thread_map.set = AsyncMock()
    notifier = AsyncMock()
    signal_source = MessagingSignalSource()
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=[0.1] * 10)

    processor = InboundMessageProcessor(
        memory_store=memory,
        contact_channel_store=contacts,
        thread_channel_map=thread_map,
        notifier=notifier,
        signal_source=signal_source,
        embedder=embedder,
        automated_sender_patterns=automated_patterns or [],
        llm_client=None,
    )
    return processor, memory, thread_map, signal_source


# ── _is_automated ─────────────────────────────────────────────────────────────

def test_is_automated_noreply():
    assert _is_automated("noreply@github.com", {}, [])


def test_is_automated_list_unsubscribe_header():
    assert _is_automated("news@example.com", {"List-Unsubscribe": "<mailto:unsub@example.com>"}, [])


def test_is_automated_precedence_bulk():
    assert _is_automated("promo@shop.com", {"Precedence": "bulk"}, [])


def test_is_not_automated_normal_sender():
    assert not _is_automated("alice@example.com", {}, [])


def test_is_automated_custom_pattern():
    assert _is_automated("updates@myapp.com", {}, [r"updates@"])


# ── process() — automated sender ─────────────────────────────────────────────

async def test_automated_sender_writes_nothing():
    processor, memory, thread_map, signals = _make_processor()
    await processor.process(
        _msg(sender="noreply@github.com"), channel_id="gmail:ze@example.com"
    )
    memory.write_episode.assert_not_called()
    thread_map.set.assert_not_called()
    assert signals._buffer == []


# ── process() — known contact ────────────────────────────────────────────────

async def test_known_contact_writes_episode_and_signal():
    known = MagicMock()
    known.name = "Alice"
    processor, memory, thread_map, signals = _make_processor(contact=known)

    await processor.process(_msg(), channel_id="gmail:ze@example.com")

    memory.write_episode.assert_called_once()
    assert len(signals._buffer) == 1
    assert signals._buffer[0].external_ref == "msg1"


async def test_known_contact_sets_thread_map():
    known = MagicMock()
    known.name = "Alice"
    processor, memory, thread_map, _ = _make_processor(contact=known)

    await processor.process(_msg(thread_id="t99"), channel_id="gmail:ze@example.com")

    thread_map.set.assert_called_once_with("t99", "gmail:ze@example.com")


# ── process() — unknown human ────────────────────────────────────────────────

async def test_unknown_human_writes_episode_no_signal():
    processor, memory, thread_map, signals = _make_processor(contact=None, thread_channel=None)

    await processor.process(_msg(), channel_id="gmail:ze@example.com")

    memory.write_episode.assert_called_once()
    assert signals._buffer == []


# ── process() — replied-to ───────────────────────────────────────────────────

async def test_replied_to_writes_signal():
    # No contact match but thread is known
    processor, memory, thread_map, signals = _make_processor(
        contact=None,
        thread_channel="gmail:ze@example.com",
    )
    await processor.process(_msg(), channel_id="gmail:ze@example.com")

    memory.write_episode.assert_called_once()
    assert len(signals._buffer) == 1


# ── _extract_facts ────────────────────────────────────────────────────────────

async def test_extract_facts_calls_propose_facts():
    from unittest.mock import patch
    from ze_memory.types import Fact

    known = MagicMock()
    known.name = "Alice"
    processor, memory, _, _ = _make_processor(contact=known)

    llm = AsyncMock()
    llm.complete = AsyncMock(return_value='[{"predicate": "name", "value": "Alice", "confidence": 0.9}]')
    processor._llm_client = llm

    await processor._extract_facts(_msg())

    memory.propose_facts.assert_called_once()
    facts = memory.propose_facts.call_args[0][0]
    assert len(facts) == 1
    assert facts[0].value == "Alice"


async def test_extract_facts_no_llm_client_is_noop():
    processor, memory, _, _ = _make_processor()
    processor._llm_client = None
    await processor._extract_facts(_msg())
    memory.propose_facts.assert_not_called()


async def test_extract_facts_llm_error_is_swallowed():
    known = MagicMock()
    known.name = "Alice"
    processor, memory, _, _ = _make_processor(contact=known)

    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    processor._llm_client = llm

    await processor._extract_facts(_msg())  # must not raise
    memory.propose_facts.assert_not_called()
