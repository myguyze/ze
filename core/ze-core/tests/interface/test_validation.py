import pytest

from ze_core.errors import InterfaceConfigError
from ze_core.interface.types import (
    ConfirmationRequest,
    ConfirmationResponse,
    Notification,
    OutboundMessage,
)
from ze_core.interface.validation import validate_interface


# ── Helpers ───────────────────────────────────────────────────────────────────

class _ValidInline:
    confirmation_style = "inline"

    async def send(self, message: OutboundMessage) -> None: ...
    async def push(self, notification: Notification) -> None: ...
    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        return ConfirmationResponse(approved=True)


class _ValidAsync:
    confirmation_style = "async"

    async def send(self, message: OutboundMessage) -> None: ...
    async def push(self, notification: Notification) -> None: ...
    async def send_confirmation(self, request: ConfirmationRequest) -> None: ...


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestValidateInterface:
    def test_valid_inline_passes(self):
        validate_interface(_ValidInline())

    def test_valid_async_passes(self):
        validate_interface(_ValidAsync())

    def test_missing_confirmation_style_raises(self):
        class NoStyle:
            async def send(self, m): ...
            async def push(self, n): ...

        with pytest.raises(InterfaceConfigError, match="confirmation_style"):
            validate_interface(NoStyle())

    def test_invalid_confirmation_style_raises(self):
        class BadStyle:
            confirmation_style = "poll"
            async def send(self, m): ...
            async def push(self, n): ...

        with pytest.raises(InterfaceConfigError, match="'inline' or 'async'"):
            validate_interface(BadStyle())

    def test_inline_without_confirm_raises(self):
        class InlineNoConfirm:
            confirmation_style = "inline"
            async def send(self, m): ...
            async def push(self, n): ...

        with pytest.raises(InterfaceConfigError, match="confirm\\(\\)"):
            validate_interface(InlineNoConfirm())

    def test_async_without_send_confirmation_raises(self):
        class AsyncNoSend:
            confirmation_style = "async"
            async def send(self, m): ...
            async def push(self, n): ...

        with pytest.raises(InterfaceConfigError, match="send_confirmation\\(\\)"):
            validate_interface(AsyncNoSend())
