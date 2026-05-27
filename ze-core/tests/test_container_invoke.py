"""
Tests for Container.invoke() and Container.resume() — graph is fully mocked.
These tests verify the confirmation-flow wiring without needing langgraph or asyncpg.
"""
from dataclasses import dataclass, field
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.container import Container
from ze_core.interface.types import (
    ConfirmationRequest,
    ConfirmationResponse,
    InvokeResult,
    OutboundMessage,
)
from ze_core.orchestration.types import AgentResult


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _state(
    response: str = "Hello!",
    pending: bool = False,
    error: str | None = None,
) -> dict:
    result = AgentResult(agent="test", response=response) if pending else None
    return {
        "final_response": None if pending else response,
        "pending_confirmation": pending,
        "agent_result": result,
        "error": error,
    }


def _container(
    graph_states: list[dict],
    interface: object | None = None,
) -> Container:
    graph = MagicMock()
    graph.ainvoke = AsyncMock(side_effect=graph_states)
    return Container(
        settings=MagicMock(confirm_timeout_seconds=60),
        pool=None,
        checkpointer_pool=None,
        embedder=None,
        openrouter_client=None,
        router=None,
        capability_gate=None,
        memory_store=None,
        memory_consolidator=None,
        graph=graph,
        interface=interface,
    )


class _InlineInterface:
    confirmation_style: ClassVar[str] = "inline"

    def __init__(self, approve: bool = True, edit: str | None = None):
        self._approve = approve
        self._edit = edit
        self.sent: list[OutboundMessage] = []
        self.confirmations: list[ConfirmationRequest] = []

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)

    async def push(self, notification) -> None:
        pass

    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        self.confirmations.append(request)
        return ConfirmationResponse(approved=self._approve, edited_content=self._edit)


class _AsyncInterface:
    confirmation_style: ClassVar[str] = "async"

    def __init__(self):
        self.sent: list[OutboundMessage] = []
        self.confirmations: list[ConfirmationRequest] = []

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)

    async def push(self, notification) -> None:
        pass

    async def send_confirmation(self, request: ConfirmationRequest) -> None:
        self.confirmations.append(request)


# ── Container.invoke() — no confirmation ─────────────────────────────────────

class TestInvokeSimple:
    async def test_returns_final_response(self):
        c = _container([_state("Hi there!")])
        result = await c.invoke("hello", "s1")
        assert result.response == "Hi there!"
        assert result.confirmation_pending is False
        assert result.error is None

    async def test_sends_via_interface_when_set(self):
        iface = _InlineInterface()
        c = _container([_state("answer")], interface=iface)
        await c.invoke("q", "s1")
        assert len(iface.sent) == 1
        assert iface.sent[0].content == "answer"

    async def test_no_interface_does_not_raise(self):
        c = _container([_state("answer")])
        result = await c.invoke("q", "s1")
        assert result.response == "answer"

    async def test_graph_error_returned_as_error_result(self):
        c = _container([_state(error="routing failed")])
        result = await c.invoke("q", "s1")
        assert result.error == "routing failed"
        assert result.response is None

    async def test_graph_called_with_correct_prompt(self):
        c = _container([_state("ok")])
        await c.invoke("my prompt", "sess42")
        graph_input = c.graph.ainvoke.call_args[0][0]
        assert graph_input["prompt"] == "my prompt"
        assert graph_input["session_id"] == "sess42"

    async def test_thread_id_in_config(self):
        c = _container([_state("ok")])
        await c.invoke("q", "thread-123")
        config = c.graph.ainvoke.call_args[0][1]
        assert config["configurable"]["thread_id"] == "thread-123"


# ── Container.invoke() — inline confirmation ─────────────────────────────────

class TestInvokeInlineConfirmation:
    async def test_confirm_approved_resumes_graph(self):
        iface = _InlineInterface(approve=True)
        c = _container(
            [_state("draft text", pending=True), _state("executed result")],
            interface=iface,
        )
        result = await c.invoke("q", "s1")

        assert result.response == "executed result"
        assert result.confirmation_pending is False
        assert c.graph.ainvoke.call_count == 2

    async def test_confirm_approved_sends_final_response(self):
        iface = _InlineInterface(approve=True)
        c = _container(
            [_state("draft", pending=True), _state("final answer")],
            interface=iface,
        )
        await c.invoke("q", "s1")
        assert len(iface.sent) == 1
        assert iface.sent[0].content == "final answer"

    async def test_confirm_rejected_returns_draft(self):
        iface = _InlineInterface(approve=False)
        c = _container([_state("draft text", pending=True)], interface=iface)
        result = await c.invoke("q", "s1")

        assert result.response == "draft text"
        assert result.confirmation_pending is False
        # Graph not resumed
        assert c.graph.ainvoke.call_count == 1

    async def test_confirmation_request_contains_draft(self):
        iface = _InlineInterface(approve=False)
        c = _container([_state("my draft", pending=True)], interface=iface)
        await c.invoke("q", "s1")

        assert len(iface.confirmations) == 1
        assert iface.confirmations[0].content == "my draft"

    async def test_no_interface_returns_confirmation_pending(self):
        c = _container([_state("draft", pending=True)])
        result = await c.invoke("q", "s1")
        assert result.confirmation_pending is True
        assert c.graph.ainvoke.call_count == 1


# ── Container.invoke() — async confirmation ──────────────────────────────────

class TestInvokeAsyncConfirmation:
    async def test_sends_confirmation_and_returns_pending(self):
        iface = _AsyncInterface()
        c = _container([_state("draft", pending=True)], interface=iface)
        result = await c.invoke("q", "s1")

        assert result.confirmation_pending is True
        assert len(iface.confirmations) == 1
        assert iface.confirmations[0].content == "draft"

    async def test_graph_not_resumed_in_async_style(self):
        iface = _AsyncInterface()
        c = _container([_state("draft", pending=True)], interface=iface)
        await c.invoke("q", "s1")
        assert c.graph.ainvoke.call_count == 1


# ── Container.resume() ────────────────────────────────────────────────────────

class TestResume:
    async def test_resumes_graph_and_returns_response(self):
        iface = _AsyncInterface()
        c = _container([_state("resumed response")], interface=iface)
        result = await c.resume("s1")

        assert result.response == "resumed response"
        assert result.session_id == "s1"

    async def test_sends_response_via_interface(self):
        iface = _AsyncInterface()
        c = _container([_state("final")], interface=iface)
        await c.resume("s1")
        assert len(iface.sent) == 1
        assert iface.sent[0].content == "final"

    async def test_resume_error_returned(self):
        iface = _AsyncInterface()
        c = _container([_state(error="agent failed")], interface=iface)
        result = await c.resume("s1")
        assert result.error == "agent failed"
        assert result.response is None

    async def test_resume_calls_ainvoke_with_none(self):
        c = _container([_state("ok")])
        await c.resume("thread-99")
        graph_input = c.graph.ainvoke.call_args[0][0]
        assert graph_input is None

    async def test_resume_thread_id_in_config(self):
        c = _container([_state("ok")])
        await c.resume("thread-99")
        config = c.graph.ainvoke.call_args[0][1]
        assert config["configurable"]["thread_id"] == "thread-99"


# ── Container.from_config() — interface validation ───────────────────────────

class TestFromConfigInterfaceValidation:
    def test_validate_interface_called_on_misconfigured(self):
        from ze_core.errors import InterfaceConfigError

        class BadInterface:
            pass  # no confirmation_style

        with pytest.raises(InterfaceConfigError):
            from ze_core.interface.validation import validate_interface
            validate_interface(BadInterface())

    def test_valid_interface_passes_validation(self):
        from ze_core.interface.validation import validate_interface

        iface = _InlineInterface()
        validate_interface(iface)  # should not raise
