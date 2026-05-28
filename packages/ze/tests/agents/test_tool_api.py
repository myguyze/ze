"""Tests for the tool registry, call_tool() enforcement, and validate_registry()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.orchestration.base_agent import BaseAgent, _truncate_messages
import ze_core.orchestration.tool as _tool_mod
from ze_core.orchestration.tool import ToolAccess, ToolSpec, get_tool, registered_tools, tool

_tool_registry = _tool_mod._tools
from ze_core.orchestration.types import AgentContext, AgentResult, ToolCall
from ze_core.capability.types import GateDecision
from ze_core.errors import AgentConfigError, ToolBlockedError, UnknownToolError
from ze.logging import configure_logging
from ze_core.memory.types import MemoryContext


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Fixtures — minimal concrete agent for testing call_tool() ─────────────────

class _ConcreteAgent(BaseAgent):
    name = "test_concrete"
    tools: list[str] = []

    async def run(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(agent=self.name, response="ok")

    async def stream(self, ctx):
        yield "ok"


def make_agent(_settings=None) -> _ConcreteAgent:
    return _ConcreteAgent()


def make_ctx(gate_decision: GateDecision = GateDecision.EXECUTE) -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt="test",
        intent="read",
        gate_decision=gate_decision,
        memory=MemoryContext(),
    )


# ── @tool decorator ───────────────────────────────────────────────────────────

def test_tool_decorator_registers_in_registry():
    @tool(access=ToolAccess.READ, description="A test read tool.")
    async def _test_read_tool(query: str) -> ToolCall: ...

    assert "_test_read_tool" in _tool_registry
    spec = _tool_registry["_test_read_tool"]
    assert spec.access == ToolAccess.READ
    assert spec.description == "A test read tool."


def test_tool_decorator_accepts_string_access():
    @tool(access="write", description="A write tool.")
    async def _test_write_tool(body: str) -> ToolCall: ...

    assert _tool_registry["_test_write_tool"].access == ToolAccess.WRITE


def test_tool_decorator_preserves_function():
    @tool(access=ToolAccess.READ, description="Preserved.")
    async def _preserved(x: int) -> ToolCall: ...

    import asyncio
    # decorated function is still callable directly
    assert callable(_preserved)


def test_tool_params_extracted_from_signature():
    import inspect

    @tool(access=ToolAccess.READ, description="Param test.")
    async def _param_tool(query: str, max_results: int = 5) -> ToolCall: ...

    spec = _tool_registry["_param_tool"]
    sig = inspect.signature(spec.func)
    assert "query" in sig.parameters
    assert "max_results" in sig.parameters
    assert sig.parameters["query"].default is inspect.Parameter.empty
    assert sig.parameters["max_results"].default == 5


def test_get_tool_raises_for_unknown():
    with pytest.raises(UnknownToolError, match="no_such_tool"):
        get_tool("no_such_tool")


def test_registered_tools_returns_snapshot():
    snap = registered_tools()
    assert isinstance(snap, dict)
    # snapshot is independent of the live registry
    snap["_fake"] = MagicMock()
    assert "_fake" not in _tool_registry


# ── call_tool() — EXECUTE mode ────────────────────────────────────────────────

async def test_call_tool_execute_read_tool_runs():
    called_with: dict = {}

    @tool(access=ToolAccess.READ, description="Execute read.")
    async def _exec_read(query: str) -> ToolCall:
        called_with["query"] = query
        return ToolCall(tool_name="_exec_read", args={"query": query}, result="ok", duration_ms=1, success=True)

    agent = make_agent()
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_exec_read", ctx, query="hello")

    assert result.success is True
    assert called_with["query"] == "hello"


async def test_call_tool_execute_write_tool_runs():
    @tool(access=ToolAccess.WRITE, description="Execute write.")
    async def _exec_write(body: str) -> ToolCall:
        return ToolCall(tool_name="_exec_write", args={"body": body}, result="sent", duration_ms=1, success=True)

    agent = make_agent()
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_exec_write", ctx, body="hello")

    assert result.success is True
    assert result.is_draft is False


# ── call_tool() — DRAFT mode ──────────────────────────────────────────────────

async def test_call_tool_draft_read_tool_runs():
    @tool(access=ToolAccess.READ, description="Draft read.")
    async def _draft_read(query: str) -> ToolCall:
        return ToolCall(tool_name="_draft_read", args={}, result="data", duration_ms=1, success=True)

    agent = make_agent()
    ctx = make_ctx(GateDecision.DRAFT)
    result = await agent.call_tool("_draft_read", ctx, query="hello")

    assert result.success is True
    assert result.is_draft is False


async def test_call_tool_draft_suppresses_write_tool():
    side_effects: list = []

    @tool(access=ToolAccess.WRITE, description="Draft write.")
    async def _draft_write(body: str) -> ToolCall:
        side_effects.append(body)  # should never run
        return ToolCall(tool_name="_draft_write", args={}, result=None, duration_ms=1, success=True)

    agent = make_agent()
    ctx = make_ctx(GateDecision.DRAFT)
    result = await agent.call_tool("_draft_write", ctx, body="secret")

    assert result.is_draft is True
    assert result.success is False
    assert "draft" in (result.error or "")
    assert side_effects == []  # function body never executed


# ── call_tool() — BLOCKED mode ────────────────────────────────────────────────

async def test_call_tool_blocked_raises_for_read_tool():
    @tool(access=ToolAccess.READ, description="Blocked read.")
    async def _blocked_read(query: str) -> ToolCall: ...

    agent = make_agent()
    ctx = make_ctx(GateDecision.BLOCKED)

    with pytest.raises(ToolBlockedError):
        await agent.call_tool("_blocked_read", ctx, query="x")


async def test_call_tool_blocked_raises_for_write_tool():
    @tool(access=ToolAccess.WRITE, description="Blocked write.")
    async def _blocked_write(body: str) -> ToolCall: ...

    agent = make_agent()
    ctx = make_ctx(GateDecision.BLOCKED)

    with pytest.raises(ToolBlockedError):
        await agent.call_tool("_blocked_write", ctx, body="x")


# ── call_tool() — unknown tool ────────────────────────────────────────────────

async def test_call_tool_raises_for_unregistered_tool():
    agent = make_agent()
    ctx = make_ctx()

    with pytest.raises(UnknownToolError):
        await agent.call_tool("nonexistent_tool", ctx)


# ── call_tool() — tool raises unexpectedly ────────────────────────────────────

async def test_call_tool_wraps_unexpected_exception():
    @tool(access=ToolAccess.READ, description="Crashing tool.")
    async def _crashing_tool(query: str) -> ToolCall:
        raise RuntimeError("kaboom")

    agent = make_agent()
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_crashing_tool", ctx, query="x")

    assert result.success is False
    assert "kaboom" in (result.error or "")
    assert result.is_draft is False


# ── BaseAgent config helpers ──────────────────────────────────────────────────

def test_model_returns_class_default():
    class _ResearchLike(BaseAgent):
        name = "research"
        model = "anthropic/claude-sonnet-4-5"
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    agent = _ResearchLike()
    assert "anthropic" in agent._model()


def test_timeout_returns_class_default():
    class _ResearchLike(BaseAgent):
        name = "research"
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    agent = _ResearchLike()
    assert agent._timeout() > 0


def test_format_memory_empty():
    agent = make_agent()
    ctx = make_ctx()
    assert agent._format_memory(ctx) == "(none)"


def test_format_memory_with_facts():
    from ze_core.memory.types import UserFact
    agent = make_agent()
    ctx = AgentContext(
        session_id="s1", prompt="x", intent="read",
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(facts=[UserFact(key="name", value="Alice")]),
    )
    result = agent._format_memory(ctx)
    assert "name: Alice" in result


# ── validate_registry() ───────────────────────────────────────────────────────

def test_validate_registry_passes_with_valid_config():
    from ze.agents.bootstrap import validate_registry
    import ze.agents.research.agent  # noqa: F401
    import ze.agents.companion.agent  # noqa: F401
    validate_registry()


def test_validate_registry_fails_on_unknown_tool():
    from ze.agents.bootstrap import validate_registry
    from ze_core.orchestration.registry import _registry

    class _BadAgent(BaseAgent):
        name = "_bad_agent_unknown_tool"
        description = "bad"
        tools = ["this_tool_does_not_exist"]
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    _registry["_bad_agent_unknown_tool"] = _BadAgent
    try:
        with pytest.raises(AgentConfigError, match="this_tool_does_not_exist"):
            validate_registry()
    finally:
        _registry.pop("_bad_agent_unknown_tool", None)


def test_validate_registry_fails_on_missing_capability_intent():
    from ze.agents.bootstrap import validate_registry
    from ze_core.orchestration.registry import _registry
    from ze_core.capability.types import Mode

    class _BadIntentAgent(BaseAgent):
        name = "_bad_intent_agent"
        description = "bad"
        tools: list[str] = []
        intent_map = {"destroy": "obliterate"}
        capabilities = {"read": Mode.AUTONOMOUS}
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    _registry["_bad_intent_agent"] = _BadIntentAgent
    try:
        with pytest.raises(AgentConfigError, match="destroy"):
            validate_registry()
    finally:
        _registry.pop("_bad_intent_agent", None)


# ── ToolSpec.llm_schema() ─────────────────────────────────────────────────────

def _make_schema_tool(fn):
    """Register fn as a tool and return its ToolSpec."""
    from ze_core.orchestration.tool import ToolAccess, tool as tool_dec, get_tool
    tool_dec(access=ToolAccess.READ, description=fn.__doc__ or "test")(fn)
    return get_tool(fn.__name__)


def test_llm_schema_basic_string_param():
    async def _schema_str(query: str) -> ToolCall: ...
    _schema_str.__doc__ = "A string tool."
    spec = _make_schema_tool(_schema_str)
    schema = spec.llm_schema()
    assert schema["name"] == "_schema_str"
    assert schema["description"] == "A string tool."
    props = schema["parameters"]["properties"]
    assert "query" in props
    assert props["query"]["type"] == "string"
    assert "query" in schema["parameters"]["required"]


def test_llm_schema_excludes_complex_type_params():
    """Params typed as domain objects (e.g. client) must not appear in schema."""
    from ze_core.openrouter.client import OpenRouterClient

    async def _schema_with_client(query: str, client: OpenRouterClient) -> ToolCall: ...
    _schema_with_client.__doc__ = "Client excluded."
    spec = _make_schema_tool(_schema_with_client)
    schema = spec.llm_schema()
    props = schema["parameters"]["properties"]
    assert "query" in props
    assert "client" not in props


def test_llm_schema_optional_param_not_required():
    from typing import Optional

    async def _schema_optional(query: str, limit: Optional[int] = None) -> ToolCall: ...
    _schema_optional.__doc__ = "Optional param."
    spec = _make_schema_tool(_schema_optional)
    schema = spec.llm_schema()
    required = schema["parameters"].get("required", [])
    assert "query" in required
    assert "limit" not in required


def test_llm_schema_default_param_not_required():
    async def _schema_default(query: str, max_results: int = 5) -> ToolCall: ...
    _schema_default.__doc__ = "Default param."
    spec = _make_schema_tool(_schema_default)
    schema = spec.llm_schema()
    required = schema["parameters"].get("required", [])
    assert "query" in required
    assert "max_results" not in required


def test_llm_schema_integer_type():
    async def _schema_int(count: int) -> ToolCall: ...
    _schema_int.__doc__ = "Integer."
    spec = _make_schema_tool(_schema_int)
    props = spec.llm_schema()["parameters"]["properties"]
    assert props["count"]["type"] == "integer"


def test_llm_schema_float_type():
    async def _schema_float(ratio: float) -> ToolCall: ...
    _schema_float.__doc__ = "Float."
    spec = _make_schema_tool(_schema_float)
    props = spec.llm_schema()["parameters"]["properties"]
    assert props["ratio"]["type"] == "number"


def test_llm_schema_bool_type():
    async def _schema_bool(flag: bool) -> ToolCall: ...
    _schema_bool.__doc__ = "Bool."
    spec = _make_schema_tool(_schema_bool)
    props = spec.llm_schema()["parameters"]["properties"]
    assert props["flag"]["type"] == "boolean"


def test_llm_schema_all_complex_excluded_yields_empty_properties():
    from ze_core.openrouter.client import OpenRouterClient as ORC

    async def _schema_all_complex(client: ORC, model: str) -> ToolCall: ...
    _schema_all_complex.__doc__ = "Complex only."
    spec = _make_schema_tool(_schema_all_complex)
    schema = spec.llm_schema()
    # model (str) is visible, client (ORC) is not
    props = schema["parameters"]["properties"]
    assert "model" in props
    assert "client" not in props


# ── agentic_loop() ────────────────────────────────────────────────────────────

def _make_loop_agent(settings) -> _ConcreteAgent:
    agent = _ConcreteAgent(settings=settings)
    agent.tools = ["openrouter:web_search"]
    return agent


def make_loop_ctx() -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt="test",
        intent="read",
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(),
        messages=[{"role": "user", "content": "test"}],
    )


async def test_agentic_loop_returns_text_immediately():
    """LLM returns text on first call — no tool calls, no iterations."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=("Answer.", None))
    agent = _make_loop_agent(settings)

    text, tool_calls = await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=[{"role": "user", "content": "test"}],
        system="sys",
        tool_names=["openrouter:web_search"],
    )
    assert text == "Answer."
    assert tool_calls == []
    client.complete_with_tools.assert_awaited_once()


async def test_agentic_loop_one_tool_call_round_trip():
    """LLM calls openrouter:web_search once (server tool), then returns text."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "openrouter:web_search", "arguments": {"query": "test"}}]),
        ("Final answer.", None),
    ])
    client.complete = AsyncMock(return_value="Final answer.")

    agent = _make_loop_agent(settings)
    messages = [{"role": "user", "content": "test"}]
    text, tool_calls = await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=messages,
        system="sys",
        tool_names=["openrouter:web_search"],
    )

    assert text == "Final answer."
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "openrouter:web_search"
    assert tool_calls[0].success is True


async def test_agentic_loop_appends_tool_turns_to_messages():
    """Server tool call and result messages are appended to the messages list."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "openrouter:web_search", "arguments": {"query": "q"}}]),
        ("Done.", None),
    ])

    agent = _make_loop_agent(settings)
    messages = [{"role": "user", "content": "q"}]
    await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=messages,
        system="sys",
        tool_names=["openrouter:web_search"],
    )

    # messages should now contain: user | assistant(tool_calls) | tool(result)
    roles = [m["role"] for m in messages]
    assert "assistant" in roles
    assert "tool" in roles


async def test_agentic_loop_forces_text_after_max_iterations():
    """After max_iterations, falls back to plain complete() without tools."""
    tool_call = (None, [{"id": "c1", "name": "openrouter:web_search", "arguments": {"query": "q"}}])
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=tool_call)
    client.complete = AsyncMock(return_value="Forced final answer.")

    agent = _make_loop_agent(settings)
    text, tool_calls = await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=[{"role": "user", "content": "q"}],
        system="sys",
        tool_names=["openrouter:web_search"],
        max_iterations=2,
    )

    assert text == "Forced final answer."
    assert len(tool_calls) == 2
    client.complete.assert_awaited_once()


async def test_agentic_loop_passes_schemas_to_client():
    """Tool schemas are generated and forwarded to complete_with_tools."""
    received_tools: list = []

    async def _mock_cwt(messages, model, tools, system=None, **kwargs):
        received_tools.extend(tools)
        return ("Done.", None)

    client = AsyncMock()
    client.complete_with_tools = _mock_cwt

    agent = _make_loop_agent(settings)
    await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=[{"role": "user", "content": "q"}],
        system="sys",
        tool_names=["openrouter:web_search"],
    )

    assert len(received_tools) == 1
    assert received_tools[0]["name"] == "openrouter:web_search"


async def test_agentic_loop_raises_agent_error_on_none_none_response():
    """complete_with_tools returning (None, None) raises AgentError, not AssertionError."""
    from ze_core.errors import AgentError

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(None, None))

    agent = _make_loop_agent(settings)
    with pytest.raises(AgentError, match="no text and no tool calls"):
        await agent.agentic_loop(
            make_loop_ctx(),
            client=client,
            messages=[{"role": "user", "content": "q"}],
            system="sys",
            tool_names=["openrouter:web_search"],
        )


async def test_agentic_loop_empty_string_raises_agent_error():
    """Empty text + no tool calls from complete_with_tools raises AgentError, not returns ''."""
    from ze_core.errors import AgentError

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=("", None))

    agent = _make_loop_agent(settings)
    with pytest.raises(AgentError, match="no text and no tool calls"):
        await agent.agentic_loop(
            make_loop_ctx(),
            client=client,
            messages=[{"role": "user", "content": "q"}],
            system="sys",
            tool_names=["openrouter:web_search"],
        )


async def test_agentic_loop_forwards_max_tokens():
    """max_tokens is forwarded to complete_with_tools."""
    received_kwargs: list[dict] = []

    async def _mock_cwt(messages, model, tools, system=None, **kwargs):
        received_kwargs.append(kwargs)
        return ("Done.", None)

    client = AsyncMock()
    client.complete_with_tools = _mock_cwt

    agent = _make_loop_agent(settings)
    await agent.agentic_loop(
        make_loop_ctx(),
        client=client,
        messages=[{"role": "user", "content": "q"}],
        system="sys",
        tool_names=["openrouter:web_search"],
        max_tokens=4000,
    )

    assert received_kwargs[0].get("max_tokens") == 4000


# ── _truncate_messages ────────────────────────────────────────────────────────

def test_truncate_removes_full_round_atomically():
    """Removing a round removes the assistant turn AND its tool results together."""
    from ze_core.orchestration.base_agent import _truncate_messages

    messages = [
        {"role": "user", "content": "find me prospects"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 4000},
        {"role": "assistant", "content": "Here are the results."},
    ]

    _truncate_messages(messages, max_tokens=10)

    roles = [m["role"] for m in messages]
    # assistant turn with tool_calls must not remain without its tool result
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_ids = {tc["id"] for tc in msg["tool_calls"]}
            result_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
            assert tool_ids <= result_ids, "orphaned assistant turn after truncation"


def test_truncate_removes_multi_tool_round_atomically():
    """An assistant turn with two tool calls has both results removed together."""
    from ze_core.orchestration.base_agent import _truncate_messages

    messages = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "web_search", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 2000},
        {"role": "tool", "tool_call_id": "c2", "content": "x" * 2000},
        {"role": "assistant", "content": "Done."},
    ]

    _truncate_messages(messages, max_tokens=10)

    # Either the whole round is gone or the whole round remains — never partial
    assistant_with_tools = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
    for msg in assistant_with_tools:
        tool_ids = {tc["id"] for tc in msg["tool_calls"]}
        result_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
        assert tool_ids <= result_ids, "partial round removal left orphaned assistant turn"


def test_truncate_never_removes_protected_messages():
    """Last 4 messages are never removed even when over budget."""
    from ze_core.orchestration.base_agent import _truncate_messages

    tail = [
        {"role": "tool", "tool_call_id": "recent-1", "content": "recent result"},
        {"role": "assistant", "content": "working on it"},
        {"role": "tool", "tool_call_id": "recent-2", "content": "another result"},
        {"role": "user", "content": "ok"},
    ]
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "old-1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "old-1", "content": "old content " * 200},
    ] + tail

    _truncate_messages(messages, max_tokens=10)

    for msg in tail:
        assert msg in messages, f"protected message was removed: {msg}"
