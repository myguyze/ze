"""Tests for Channel ABC, ChannelRegistry, and channel types."""
from datetime import datetime, timezone

import pytest

from ze_communication.channel import Channel
from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelType, Message, SentMessage, Thread, ThreadMessage
from ze_agents.errors import ChannelError, ChannelNotFoundError


# ── stub implementation ───────────────────────────────────────────────────────

class StubChannel(Channel):
    def __init__(self, ctype: ChannelType = ChannelType.EMAIL) -> None:
        self._type = ctype

    @property
    def channel_type(self) -> ChannelType:
        return self._type

    async def send(self, message: Message) -> SentMessage:
        return SentMessage(
            message_id="msg-1",
            thread_id="thread-1",
            channel_type=self._type,
            sent_at=datetime.now(timezone.utc),
        )

    async def get_thread(self, thread_id: str) -> Thread:
        return Thread(thread_id=thread_id, channel_type=self._type)

    async def poll_replies(self, thread_ids: list[str], since: datetime) -> list[ThreadMessage]:
        return []


# ── TestChannelTypes ──────────────────────────────────────────────────────────

class TestChannelTypes:
    def test_channel_type_values(self):
        assert ChannelType.EMAIL == "email"
        assert ChannelType.LINKEDIN == "linkedin"
        assert ChannelType.WHATSAPP == "whatsapp"

    def test_message_fields(self):
        m = Message(channel_type=ChannelType.EMAIL, to="a@b.com", body="hello")
        assert m.to == "a@b.com"
        assert m.body == "hello"
        assert m.subject is None
        assert m.thread_id is None

    def test_sent_message_fields(self):
        now = datetime.now(timezone.utc)
        s = SentMessage(message_id="x", thread_id="t", channel_type=ChannelType.EMAIL, sent_at=now)
        assert s.message_id == "x"
        assert s.thread_id == "t"

    def test_thread_message_fields(self):
        now = datetime.now(timezone.utc)
        tm = ThreadMessage(message_id="m", sender="alice", body="hi", sent_at=now, is_outbound=False)
        assert tm.body == "hi"
        assert not tm.is_outbound

    def test_thread_defaults(self):
        t = Thread(thread_id="t1", channel_type=ChannelType.EMAIL)
        assert t.messages == []


# ── TestChannelABC ────────────────────────────────────────────────────────────

class TestChannelABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Channel()  # type: ignore[abstract]

    def test_stub_is_channel_instance(self):
        assert isinstance(StubChannel(), Channel)

    async def test_stub_send_returns_sent_message(self):
        ch = StubChannel()
        msg = Message(channel_type=ChannelType.EMAIL, to="bob@example.com", body="test")
        sent = await ch.send(msg)
        assert isinstance(sent, SentMessage)
        assert sent.channel_type == ChannelType.EMAIL

    async def test_stub_get_thread_returns_thread(self):
        ch = StubChannel()
        thread = await ch.get_thread("thread-1")
        assert thread.thread_id == "thread-1"

    async def test_stub_poll_replies_returns_list(self):
        ch = StubChannel()
        replies = await ch.poll_replies(["t1"], since=datetime.now(timezone.utc))
        assert replies == []


# ── TestChannelRegistry ───────────────────────────────────────────────────────

class TestChannelRegistry:
    def test_get_registered_channel(self):
        ch = StubChannel(ChannelType.EMAIL)
        reg = ChannelRegistry([ch])
        assert reg.get(ChannelType.EMAIL) is ch

    def test_get_missing_raises(self):
        reg = ChannelRegistry([])
        with pytest.raises(ChannelNotFoundError):
            reg.get(ChannelType.EMAIL)

    def test_channel_not_found_is_channel_error(self):
        reg = ChannelRegistry([])
        with pytest.raises(ChannelError):
            reg.get(ChannelType.EMAIL)

    def test_available_returns_types(self):
        reg = ChannelRegistry([StubChannel(ChannelType.EMAIL), StubChannel(ChannelType.WHATSAPP)])
        assert set(reg.available()) == {ChannelType.EMAIL, ChannelType.WHATSAPP}

    def test_available_empty(self):
        reg = ChannelRegistry([])
        assert reg.available() == []

    def test_last_channel_wins_for_same_type(self):
        ch1 = StubChannel(ChannelType.EMAIL)
        ch2 = StubChannel(ChannelType.EMAIL)
        reg = ChannelRegistry([ch1, ch2])
        assert reg.get(ChannelType.EMAIL) is ch2
