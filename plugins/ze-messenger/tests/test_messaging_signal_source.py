from datetime import datetime, timezone

from ze_communication.types import ChannelType, InboundMessage
from ze_messenger.signals import MessagingSignalSource


def _msg(message_id: str = "msg1") -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        channel_type=ChannelType.EMAIL,
        sender="alice@example.com",
        subject="Hello",
        body="Hi there",
        thread_id="thread1",
        received_at=datetime(2026, 6, 26, 10, 0, tzinfo=timezone.utc),
    )


def test_source_key():
    assert MessagingSignalSource.source_key == "messaging"


async def test_push_then_poll_drains_buffer():
    source = MessagingSignalSource()
    source.push(_msg("m1"))
    source.push(_msg("m2"))

    signals = await source.poll(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(signals) == 2
    assert {s.external_ref for s in signals} == {"m1", "m2"}


async def test_poll_drains_buffer():
    source = MessagingSignalSource()
    source.push(_msg("m1"))
    await source.poll(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    # Buffer empty after drain
    second = await source.poll(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert second == []


async def test_signal_has_correct_fields():
    source = MessagingSignalSource()
    msg = _msg("msgX")
    source.push(msg)
    signals = await source.poll(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = signals[0]
    assert s.source == "messaging"
    assert s.external_ref == "msgX"
    assert s.title == "Hello"
    assert "alice@example.com" in [e.name for e in s.entities]
    assert s.magnitude == 0.0
    assert s.payload["thread_id"] == "thread1"
