import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.capability.types import GateDecision
from ze_core.errors import AgentTimeoutError
from ze_core.memory.types import MemoryContext
from ze_core.orchestration import agent, clear_registry, register_instance
from ze_core.orchestration.nodes.execution import (
    await_confirmation,
    capability_check,
    draft_response,
    execute_tool,
)
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.routing.types import RoutingEnvelope, SubTask


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


def _make_agent_class(name: str, response: str = "ok", timeout: int = 30):
    class _A:
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response=response)

    _A.__name__ = f"Agent_{name}"
    _A.name = name
    _A.description = f"Agent {name}"
    _A.enabled = True
    _A.timeout = timeout
    return _A


def _register_and_wire(name: str, response: str = "ok", timeout: int = 30):
    cls = _make_agent_class(name, response, timeout)
    agent(cls)
    instance = object.__new__(cls)
    instance.run = cls.run.__get__(instance, cls)
    instance.stream = AsyncMock(side_effect=NotImplementedError)
    register_instance(name, instance)
    return instance


def _envelope(agent_name: str, intent: str = "read", is_compound: bool = False,
              is_sequential: bool = False, subtasks: list | None = None) -> RoutingEnvelope:
    if subtasks is None:
        subtasks = [SubTask(agent=agent_name, intent=intent, prompt="do it")]
    return RoutingEnvelope(
        primary_agent=agent_name,
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=subtasks,
        requires_synthesis=is_compound and not is_sequential,
        is_sequential=is_sequential,
    )


def _ctx(agent_name: str = "a", intent: str = "read") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt="do it",
        intent=intent,
        memory=MemoryContext(),
        messages=[],
    )


def _config(gate=None) -> dict:
    return {
        "configurable": {
            "capability_gate": gate,
            "thread_id": "s1",
        }
    }


# ── capability_check ──────────────────────────────────────────────────────────

class TestCapabilityCheck:
    async def test_execute_decision(self):
        from ze_core.capability import CapabilityGate, Mode
        cls = _make_agent_class("alpha")
        cls.capabilities = {"read": Mode.AUTONOMOUS}
        agent(cls)
        register_instance("alpha", object.__new__(cls))
        gate = CapabilityGate()
        state = {"envelope": _envelope("alpha"), "session_overrides": {}}
        result = await capability_check(state, _config(gate))
        assert result["gate_decision"] == GateDecision.EXECUTE

    async def test_no_envelope_returns_blocked(self):
        from ze_core.capability import CapabilityGate
        gate = CapabilityGate()
        state = {"envelope": None, "session_overrides": {}}
        result = await capability_check(state, _config(gate))
        assert result["gate_decision"] == GateDecision.BLOCKED


# ── execute_tool ──────────────────────────────────────────────────────────────

class TestExecuteTool:
    async def test_single_agent_result(self):
        _register_and_wire("a", response="hello")
        state = {
            "envelope": _envelope("a"),
            "agent_context": _ctx("a"),
            "gate_decision": GateDecision.EXECUTE,
            "image_data": None,
        }
        result = await execute_tool(state, {"configurable": {}})
        assert result["agent_result"].response == "hello"
        assert result["subtask_results"] == []

    async def test_missing_context_returns_error(self):
        state = {"envelope": None, "agent_context": None, "gate_decision": GateDecision.EXECUTE}
        result = await execute_tool(state, {"configurable": {}})
        assert "error" in result

    async def test_compound_parallel(self):
        _register_and_wire("alpha", response="r1")
        _register_and_wire("beta", response="r2")
        subtasks = [
            SubTask(agent="alpha", intent="read", prompt="p1"),
            SubTask(agent="beta", intent="read", prompt="p2"),
        ]
        env = _envelope("alpha", is_compound=True, subtasks=subtasks)
        state = {
            "envelope": env,
            "agent_context": _ctx("alpha"),
            "gate_decision": GateDecision.EXECUTE,
            "image_data": None,
        }
        result = await execute_tool(state, {"configurable": {}})
        assert result["agent_result"] is None
        assert len(result["subtask_results"]) == 2
        responses = {r.response for r in result["subtask_results"]}
        assert responses == {"r1", "r2"}

    async def test_compound_sequential(self):
        _register_and_wire("alpha", response="r1")
        _register_and_wire("beta", response="r2")
        subtasks = [
            SubTask(agent="alpha", intent="read", prompt="p1"),
            SubTask(agent="beta", intent="read", prompt="p2"),
        ]
        env = _envelope("alpha", is_compound=True, is_sequential=True, subtasks=subtasks)
        state = {
            "envelope": env,
            "agent_context": _ctx("alpha"),
            "gate_decision": GateDecision.EXECUTE,
            "image_data": None,
        }
        result = await execute_tool(state, {"configurable": {}})
        assert len(result["subtask_results"]) == 2

    async def test_timeout_raises(self):
        cls = _make_agent_class("slow", timeout=0)

        async def slow_run(self, ctx):
            await asyncio.sleep(10)
            return AgentResult(agent="slow", response="late")

        cls.run = slow_run
        agent(cls)
        instance = object.__new__(cls)
        instance.run = slow_run.__get__(instance, cls)
        register_instance("slow", instance)

        state = {
            "envelope": _envelope("slow"),
            "agent_context": _ctx("slow"),
            "gate_decision": GateDecision.EXECUTE,
            "image_data": None,
        }
        with pytest.raises(AgentTimeoutError):
            await execute_tool(state, {"configurable": {}})


# ── draft_response ────────────────────────────────────────────────────────────

class TestDraftResponse:
    async def test_sets_pending_confirmation(self):
        _register_and_wire("a", response="draft text")
        state = {
            "envelope": _envelope("a"),
            "agent_context": _ctx("a"),
            "image_data": None,
        }
        result = await draft_response(state, {"configurable": {}})
        assert result["pending_confirmation"] is True
        assert result["agent_result"].response == "draft text"

    async def test_agent_receives_draft_gate_decision(self):
        received_decision = {}

        class _DraftCapture:
            name = "capture"
            description = "capture"
            enabled = True
            timeout = 30

            async def run(self, ctx: AgentContext) -> AgentResult:
                received_decision["decision"] = ctx.gate_decision
                return AgentResult(agent="capture", response="ok")

        agent(_DraftCapture)
        instance = _DraftCapture()
        register_instance("capture", instance)

        state = {
            "envelope": _envelope("capture"),
            "agent_context": _ctx("capture"),
            "image_data": None,
        }
        await draft_response(state, {"configurable": {}})
        assert received_decision["decision"] == GateDecision.DRAFT


# ── await_confirmation ────────────────────────────────────────────────────────

class TestAwaitConfirmation:
    async def test_resets_pending_and_sets_execute(self):
        state = {
            "session_id": "s1",
            "envelope": _envelope("a"),
            "pending_confirmation": True,
        }
        result = await await_confirmation(state, {"configurable": {}})
        assert result["pending_confirmation"] is False
        assert result["gate_decision"] == GateDecision.EXECUTE
