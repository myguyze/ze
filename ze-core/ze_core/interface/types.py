from __future__ import annotations

from dataclasses import dataclass, field


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
class Notification:
    content: str
    format: str = "text"    # "text" | "markdown"
    urgency: str = "normal"  # "normal" | "high"


@dataclass
class InvokeResult:
    """Return value from Container.invoke() and Container.resume()."""
    session_id: str
    response: str | None = None
    confirmation_pending: bool = False
    error: str | None = None
