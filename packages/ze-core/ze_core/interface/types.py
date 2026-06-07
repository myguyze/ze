from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawInput:
    """Unprocessed input from any transport layer."""
    text: str | None = None
    audio: bytes | None = None
    audio_mime: str | None = None  # e.g. "audio/ogg; codecs=opus"
    image: bytes | None = None
    image_mime: str | None = None  # e.g. "image/jpeg"


@dataclass
class ProcessedInput:
    """Normalised input ready for graph invocation."""
    prompt: str
    input_modality: str = "text"   # "text" | "voice" | "image"
    image_data: bytes | None = None
    image_mime: str | None = None


@dataclass
class OutboundMessage:
    content: str
    format: str = "text"  # "text" | "markdown"


@dataclass
class ConfirmationRequest:
    content: str
    options: list[str]
    editable: bool = False
    timeout_seconds: int | None = None


@dataclass
class ConfirmationResponse:
    approved: bool
    edited_content: str | None = None
    timed_out: bool = False


@dataclass
class Action:
    """A labelled button the user can tap in a notification."""
    label: str
    payload: str  # opaque string passed back by the transport layer
    row: int = 0  # buttons sharing the same row value appear in the same keyboard row


@dataclass
class Notification:
    content: str
    format: str = "text"    # "text" | "markdown"
    urgency: str = "normal"  # "normal" | "high"
    actions: list[Action] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvokeResult:
    """Return value from Container.invoke() and Container.resume()."""
    session_id: str
    response: str | None = None
    confirmation_pending: bool = False
    error: str | None = None
