"""Tests for delegate_to_agent built-in harness tool."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.capability.types import GateDecision
from ze_core.errors import AgentAbortedError
from ze_core.orchestration import agent, clear_registry, register_instance
from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.delegate import (
    DELEGATE_TOOL_NAME,
    DELEGATE_TOOL_SCHEMA,
    _DELEGATE_MAX_DEPTH,
    run_delegate,
)
from ze_core.orchestration.tool import ToolAccess, clear_tool_registry, tool
from ze_core.orchestration.types import AbortToken, AgentContext, AgentResult


@pytest.fixture(autouse=True)
def clean():
    clear_registry()
    clear_tool_registry()
    yield
    clear_registry()
    clear_tool_registry()


def _ctx(
    depth: int = 0,
    gate_decision: GateDecision = GateDecision.EXECUTE,
    abort_token: AbortToken | None = None,
) -> AgentContext:
    extensions = {"_delegate_depth": depth} if depth else {}
    return AgentContext(
        session_id="s1",
        prompt="hello",
        intent="research",
        gate_decision=gate_decision,
        extensions=extensions,
        abort_token=abort_token,
    )


def _make_agent(agent_name: str, response: str = "agent response") -> BaseAgent:
    # Build class dynamically so `name` class attribute is set correctly.
    cls = type(
        f"_Agent_{agent_name}",
        (BaseAgent,),
        {
            "name": agent_name,
            "description": f"{agent_name} agent",
            "tools": [],
            "run": (lambda self, ctx, _r=response, _n=agent_name:
                    __import__("asyncio").coroutine(
                        lambda: AgentResult(agent=_n, response=_r)
                    )()),
        },
    )
    # Use a simpler async approach
    async def _run(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(agent=agent_name, response=response)
    cls.run = _run
    agent(cls)
    instance = cls()
    register_instance(agent_name, instance)
    return instance


# ── DELEGATE_TOOL_SCHEMA ─────────────────────────────────────────────────────

class TestDelegateToolSchema:
    def test_schema_has_correct_name(self):
        assert DELEGATE_TOOL_SCHEMA["function"]["name"] == DELEGATE_TOOL_NAME

    def test_schema_requires_agent_name_and_task(self):
        required = DELEGATE_TOOL_SCHEMA["function"]["parameters"]["required"]
        assert "agent_name" in required
        assert "task" in required

    def test_schema_context_is_optional(self):
        required = DELEGATE_TOOL_SCHEMA["function"]["parameters"]["required"]
        assert "context" not in required

    def test_schema_has_description(self):
        assert len(DELEGATE_TOOL_SCHEMA["function"]["description"]) > 10


# ── run_delegate ──────────────────────────────────────────────────────────────

class TestRunDelegate:
    async def test_delegates_to_named_agent(self):
        _make_agent("calendar", response="you have 3 events")

        tc = await run_delegate(
            {"agent_name": "calendar", "task": "list my events"},
            _ctx(),
            iteration=0,
        )

        assert tc.success is True
        assert tc.result == "you have 3 events"
        assert tc.tool_name == DELEGATE_TOOL_NAME

    async def test_context_prepended_to_prompt(self):
        received = {}

        @agent
        class _E(BaseAgent):
            name = "echo_agent"
            description = "echo"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                received["prompt"] = ctx.prompt
                received["messages"] = ctx.messages
                return AgentResult(agent="echo_agent", response="ok")

        register_instance("echo_agent", _E())

        await run_delegate(
            {"agent_name": "echo_agent", "task": "do X", "context": "extra info"},
            _ctx(),
            iteration=0,
        )

        assert received["prompt"] == "extra info\n\ndo X"
        assert received["messages"] == [{"role": "user", "content": "extra info\n\ndo X"}]

    async def test_no_context_uses_task_as_prompt(self):
        received = {}

        @agent
        class _B(BaseAgent):
            name = "bare_agent"
            description = "bare"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                received["prompt"] = ctx.prompt
                return AgentResult(agent="bare_agent", response="ok")

        register_instance("bare_agent", _B())

        await run_delegate(
            {"agent_name": "bare_agent", "task": "just this"},
            _ctx(),
            iteration=0,
        )

        assert received["prompt"] == "just this"

    async def test_inherits_gate_decision(self):
        received = {}

        @agent
        class _G(BaseAgent):
            name = "gate_agent"
            description = "gate"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                received["gate"] = ctx.gate_decision
                return AgentResult(agent="gate_agent", response="ok")

        register_instance("gate_agent", _G())

        await run_delegate(
            {"agent_name": "gate_agent", "task": "t"},
            _ctx(gate_decision=GateDecision.DRAFT),
            iteration=0,
        )


        assert received["gate"] == GateDecision.DRAFT

    async def test_inherits_abort_token(self):
        received = {}
        token = AbortToken()

        @agent
        class _T(BaseAgent):
            name = "token_agent"
            description = "token"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                received["token"] = ctx.abort_token
                return AgentResult(agent="token_agent", response="ok")

        register_instance("token_agent", _T())

        await run_delegate(
            {"agent_name": "token_agent", "task": "t"},
            _ctx(abort_token=token),
            iteration=0,
        )


        assert received["token"] is token

    async def test_depth_incremented_in_sub_ctx(self):
        received = {}

        @agent
        class _D(BaseAgent):
            name = "depth_agent"
            description = "depth"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                received["depth"] = ctx.extensions.get("_delegate_depth", 0)
                return AgentResult(agent="depth_agent", response="ok")

        register_instance("depth_agent", _D())

        await run_delegate(
            {"agent_name": "depth_agent", "task": "t"},
            _ctx(depth=1),
            iteration=0,
        )

        assert received["depth"] == 2

    async def test_depth_limit_returns_error_toolcall(self):
        _make_agent("deep_agent")

        tc = await run_delegate(
            {"agent_name": "deep_agent", "task": "t"},
            _ctx(depth=_DELEGATE_MAX_DEPTH),
            iteration=0,
        )

        assert tc.success is False
        assert "depth limit" in tc.error

    async def test_unknown_agent_returns_error_toolcall(self):
        tc = await run_delegate(
            {"agent_name": "nonexistent", "task": "t"},
            _ctx(),
            iteration=0,
        )

        assert tc.success is False
        assert tc.error is not None

    async def test_agent_exception_returns_error_toolcall(self):
        @agent
        class _C(BaseAgent):
            name = "crash_agent"
            description = "crash"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                raise RuntimeError("agent exploded")

        register_instance("crash_agent", _C())

        tc = await run_delegate(
            {"agent_name": "crash_agent", "task": "t"},
            _ctx(),
            iteration=0,
        )

        assert tc.success is False
        assert "agent exploded" in tc.error

    async def test_agent_aborted_error_propagates(self):
        # AgentAbortedError must not be swallowed — it must propagate so the
        # parent loop also aborts immediately rather than waiting for the next
        # iteration's abort-token check.
        @agent
        class _A(BaseAgent):
            name = "aborting_agent"
            description = "aborts"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                raise AgentAbortedError("sub aborted")

        register_instance("aborting_agent", _A())

        with pytest.raises(AgentAbortedError, match="sub aborted"):
            await run_delegate(
                {"agent_name": "aborting_agent", "task": "t"},
                _ctx(),
                iteration=0,
            )

    async def test_shared_abort_token_propagates_through_loop(self):
        # When a shared abort token fires inside the sub-agent's run(),
        # AgentAbortedError propagates back through run_delegate and up through
        # the parent agentic_loop — the parent loop does not continue.
        token = AbortToken()

        @agent
        class _Sub(BaseAgent):
            name = "token_aborting_agent"
            description = "aborts via token"
            tools = []
            async def run(self, ctx: AgentContext) -> AgentResult:
                raise AgentAbortedError("token fired")

        register_instance("token_aborting_agent", _Sub())

        @agent
        class _Parent(BaseAgent):
            name = "parent_agent"
            description = "delegates"
            tools = [DELEGATE_TOOL_NAME]
            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="parent_agent", response="ok")

        register_instance("parent_agent", _Parent())

        client = MagicMock()
        client.complete_with_tools = AsyncMock(side_effect=[
            (None, [{"id": "d1", "name": DELEGATE_TOOL_NAME,
                     "arguments": {"agent_name": "token_aborting_agent", "task": "t"}}]),
        ])
        client.complete = AsyncMock(return_value="fallback")

        parent = _Parent()
        ctx = AgentContext(
            session_id="s1", prompt="q", intent="parent_agent", abort_token=token
        )

        with pytest.raises(AgentAbortedError):
            await parent.agentic_loop(ctx, client, [{"role": "user", "content": "q"}], system="s")


# ── delegate in agentic_loop ─────────────────────────────────────────────────

class TestDelegateInAgenticLoop:
    def _client(self, responses):
        client = MagicMock()
        client.complete_with_tools = AsyncMock(side_effect=responses)
        client.complete = AsyncMock(return_value="fallback")
        return client

    def _loop_agent(self) -> BaseAgent:
        @agent
        class _L(BaseAgent):
            name = "loop_agent"
            description = "loop"
            tools = [DELEGATE_TOOL_NAME]
            async def run(self, ctx: AgentContext) -> AgentResult:
                return AgentResult(agent="loop_agent", response="ok")

        instance = _L()
        register_instance("loop_agent", instance)
        return instance

    async def test_delegate_schema_included_when_tool_listed(self):
        a = self._loop_agent()
        captured_schemas = []

        async def _capture(messages, model, tools, system, max_tokens):
            captured_schemas.extend(tools)
            return ("done", None)

        client = MagicMock()
        client.complete_with_tools = AsyncMock(side_effect=_capture)
        messages = [{"role": "user", "content": "q"}]
        ctx = AgentContext(session_id="s1", prompt="q", intent="loop_agent")

        await a.agentic_loop(ctx, client, messages, system="s")

        names = [s["function"]["name"] for s in captured_schemas]
        assert DELEGATE_TOOL_NAME in names

    async def test_loop_calls_delegate_when_llm_requests(self):
        _make_agent("target_agent", response="target result")
        a = self._loop_agent()

        client = self._client([
            (None, [{"id": "d1", "name": DELEGATE_TOOL_NAME,
                     "arguments": {"agent_name": "target_agent", "task": "sub task"}}]),
            ("final answer", None),
        ])
        ctx = AgentContext(session_id="s1", prompt="q", intent="loop_agent")
        messages = [{"role": "user", "content": "q"}]

        text, calls = await a.agentic_loop(ctx, client, messages, system="s")

        assert text == "final answer"
        assert len(calls) == 1
        assert calls[0].tool_name == DELEGATE_TOOL_NAME
        assert calls[0].success is True
        assert calls[0].result == "target result"
