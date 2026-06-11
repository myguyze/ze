from __future__ import annotations

from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from ze_agents.interface.types import (
    ConfirmationRequest,
    ConfirmationResponse,
    Notification,
    OutboundMessage,
    ProcessedInput,
    RawInput,
)


class InputPreprocessor(Protocol):
    """Converts raw transport input (audio, image, text) to a routing-ready prompt."""

    async def process(self, raw: RawInput, client: Any) -> ProcessedInput:
        """Normalise raw input to a text prompt and optional passthrough fields."""
        ...


@runtime_checkable
class AppInterface(Protocol):
    confirmation_style: ClassVar[Literal["inline", "async"]]

    async def send(self, message: OutboundMessage) -> None:
        """Deliver a response to the user."""

    async def push(self, notification: Notification) -> None:
        """Deliver a proactive notification. Must not raise — swallow and log errors."""

    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        """
        Required when confirmation_style == "inline".

        Block until the user responds and return their decision. Implementations
        must enforce the timeout and return ConfirmationResponse(approved=False,
        timed_out=True) on expiry.
        """
        raise NotImplementedError("inline interfaces must implement confirm()")

    async def send_confirmation(self, request: ConfirmationRequest) -> None:
        """
        Required when confirmation_style == "async".

        One-way send — deliver the confirmation UI without waiting for a response.
        The graph pauses after this call and resumes when the transport callback
        handler writes the decision into AgentState and calls graph.ainvoke(None,
        config) with the same thread_id.
        """
        raise NotImplementedError("async interfaces must implement send_confirmation()")
