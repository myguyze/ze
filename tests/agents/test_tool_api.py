"""Tests for the tool registry, call_tool() enforcement, and validate_registry()."""

import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.agents.base import BaseAgent
from ze.agents.tool import ToolAccess, ToolSpec, _tool_registry, get_tool, registered_tools, tool
from ze.agents.types import AgentContext, AgentResult, ToolCall
from ze.capability.types import GateDecision
from ze.errors import AgentConfigError, ToolBlockedError, UnknownToolError
from ze.logging import configure_logging
from ze.memory.types import MemoryContext
from ze.settings import Settings


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture
def settings():
    from ze.settings import get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


# ── Fixtures — minimal concrete agent for testing call_tool() ─────────────────

class _ConcreteAgent(BaseAgent):
    name = "test_concrete"
    tools: list[str] = []

    async def run(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(agent=self.name, response="ok")

    async def stream(self, ctx):
        yield "ok"


def make_agent(settings) -> _ConcreteAgent:
    return _ConcreteAgent(settings=settings)


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
    @tool(access=ToolAccess.READ, description="Param test.")
    async def _param_tool(query: str, max_results: int = 5) -> ToolCall: ...

    spec = _tool_registry["_param_tool"]
    names = [p.name for p in spec.params]
    assert "query" in names
    assert "max_results" in names

    query_param = next(p for p in spec.params if p.name == "query")
    assert query_param.required is True

    max_param = next(p for p in spec.params if p.name == "max_results")
    assert max_param.required is False
    assert max_param.default == 5


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

async def test_call_tool_execute_read_tool_runs(settings):
    called_with: dict = {}

    @tool(access=ToolAccess.READ, description="Execute read.")
    async def _exec_read(query: str) -> ToolCall:
        called_with["query"] = query
        return ToolCall(tool_name="_exec_read", args={"query": query}, result="ok", duration_ms=1, success=True)

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_exec_read", ctx, query="hello")

    assert result.success is True
    assert called_with["query"] == "hello"


async def test_call_tool_execute_write_tool_runs(settings):
    @tool(access=ToolAccess.WRITE, description="Execute write.")
    async def _exec_write(body: str) -> ToolCall:
        return ToolCall(tool_name="_exec_write", args={"body": body}, result="sent", duration_ms=1, success=True)

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_exec_write", ctx, body="hello")

    assert result.success is True
    assert result.is_draft is False


# ── call_tool() — DRAFT mode ──────────────────────────────────────────────────

async def test_call_tool_draft_read_tool_runs(settings):
    @tool(access=ToolAccess.READ, description="Draft read.")
    async def _draft_read(query: str) -> ToolCall:
        return ToolCall(tool_name="_draft_read", args={}, result="data", duration_ms=1, success=True)

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.DRAFT)
    result = await agent.call_tool("_draft_read", ctx, query="hello")

    assert result.success is True
    assert result.is_draft is False


async def test_call_tool_draft_suppresses_write_tool(settings):
    side_effects: list = []

    @tool(access=ToolAccess.WRITE, description="Draft write.")
    async def _draft_write(body: str) -> ToolCall:
        side_effects.append(body)  # should never run
        return ToolCall(tool_name="_draft_write", args={}, result=None, duration_ms=1, success=True)

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.DRAFT)
    result = await agent.call_tool("_draft_write", ctx, body="secret")

    assert result.is_draft is True
    assert result.success is False
    assert "draft" in (result.error or "")
    assert side_effects == []  # function body never executed


# ── call_tool() — BLOCKED mode ────────────────────────────────────────────────

async def test_call_tool_blocked_raises_for_read_tool(settings):
    @tool(access=ToolAccess.READ, description="Blocked read.")
    async def _blocked_read(query: str) -> ToolCall: ...

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.BLOCKED)

    with pytest.raises(ToolBlockedError):
        await agent.call_tool("_blocked_read", ctx, query="x")


async def test_call_tool_blocked_raises_for_write_tool(settings):
    @tool(access=ToolAccess.WRITE, description="Blocked write.")
    async def _blocked_write(body: str) -> ToolCall: ...

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.BLOCKED)

    with pytest.raises(ToolBlockedError):
        await agent.call_tool("_blocked_write", ctx, body="x")


# ── call_tool() — unknown tool ────────────────────────────────────────────────

async def test_call_tool_raises_for_unregistered_tool(settings):
    agent = make_agent(settings)
    ctx = make_ctx()

    with pytest.raises(UnknownToolError):
        await agent.call_tool("nonexistent_tool", ctx)


# ── call_tool() — tool raises unexpectedly ────────────────────────────────────

async def test_call_tool_wraps_unexpected_exception(settings):
    @tool(access=ToolAccess.READ, description="Crashing tool.")
    async def _crashing_tool(query: str) -> ToolCall:
        raise RuntimeError("kaboom")

    agent = make_agent(settings)
    ctx = make_ctx(GateDecision.EXECUTE)
    result = await agent.call_tool("_crashing_tool", ctx, query="x")

    assert result.success is False
    assert "kaboom" in (result.error or "")
    assert result.is_draft is False


# ── BaseAgent config helpers ──────────────────────────────────────────────────

def test_model_reads_from_agent_config(settings):
    # "research" is a real agent config with a model key
    class _ResearchLike(BaseAgent):
        name = "research"
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    agent = _ResearchLike(settings=settings)
    assert "claude" in agent._model() or "anthropic" in agent._model()


def test_timeout_reads_from_agent_config(settings):
    class _ResearchLike(BaseAgent):
        name = "research"
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    agent = _ResearchLike(settings=settings)
    assert agent._timeout() > 0


def test_format_memory_empty(settings):
    agent = make_agent(settings)
    ctx = make_ctx()
    assert agent._format_memory(ctx) == "(none)"


def test_format_memory_with_facts(settings):
    from ze.memory.types import UserFact
    agent = make_agent(settings)
    ctx = AgentContext(
        session_id="s1", prompt="x", intent="read",
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(facts=[UserFact(key="name", value="Alice")]),
    )
    result = agent._format_memory(ctx)
    assert "name: Alice" in result


# ── validate_registry() ───────────────────────────────────────────────────────

def test_validate_registry_passes_with_valid_config(settings):
    from ze.agents.bootstrap import validate_registry
    # Should not raise — real agents and their tools are correctly wired
    import ze.agents.research.agent  # ensure registered  # noqa: F401
    import ze.agents.companion.agent  # noqa: F401
    validate_registry(settings)


def test_validate_registry_fails_on_unknown_tool(settings):
    from ze.agents.bootstrap import validate_registry
    from ze.agents.registry import _registry

    class _BadAgent(BaseAgent):
        name = "_bad_agent_unknown_tool"
        tools = ["this_tool_does_not_exist"]
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    _registry["_bad_agent_unknown_tool"] = _BadAgent
    try:
        with pytest.raises(AgentConfigError, match="this_tool_does_not_exist"):
            validate_registry(settings)
    finally:
        _registry.pop("_bad_agent_unknown_tool", None)


def test_validate_registry_fails_on_missing_capability_intent(settings, tmp_path):
    from ze.agents.bootstrap import validate_registry
    from ze.agents.registry import _registry
    import yaml

    # Copy real config to tmp_path and inject a bad agent with an intent
    # that has no matching capabilities entry
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    real_config_path = pathlib.Path(__file__).parent.parent.parent / "config" / "config.yaml"
    with open(real_config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["agents"]["_bad_intent_agent"] = {
        "enabled": True,
        "description": "test",
        "model": "x",
        "timeout": 10,
        "intent_map": {"destroy": "obliterate"},
        "capabilities": {},
    }
    config_path.write_text(yaml.dump(cfg))

    from ze.settings import get_settings
    get_settings.cache_clear()
    bad_settings = Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=tmp_path / "config",
    )

    class _BadIntentAgent(BaseAgent):
        name = "_bad_intent_agent"
        tools: list[str] = []
        async def run(self, ctx): ...
        async def stream(self, ctx): yield ""

    _registry["_bad_intent_agent"] = _BadIntentAgent
    try:
        with pytest.raises(AgentConfigError, match="destroy"):
            validate_registry(bad_settings)
    finally:
        _registry.pop("_bad_intent_agent", None)
        get_settings.cache_clear()
