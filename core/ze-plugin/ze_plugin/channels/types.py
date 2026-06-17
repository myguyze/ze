from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ChannelType(StrEnum):
    EMAIL    = "email"
    LINKEDIN = "linkedin"
    WHATSAPP = "whatsapp"


@dataclass
class ChannelHandle:
    channel_type: ChannelType
    handle: str
    preferred: bool = False
    verified: bool = False


@dataclass
class Message:
    channel_type: ChannelType
    to: str
    body: str
    subject: str | None = None
    thread_id: str | None = None


@dataclass
class SentMessage:
    message_id: str
    thread_id: str
    channel_type: ChannelType
    sent_at: datetime


@dataclass
class ThreadMessage:
    message_id: str
    sender: str
    body: str
    sent_at: datetime
    is_outbound: bool


@dataclass
class Thread:
    thread_id: str
    channel_type: ChannelType
    messages: list[ThreadMessage] = field(default_factory=list)
