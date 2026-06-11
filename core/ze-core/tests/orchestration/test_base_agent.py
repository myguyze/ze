"""Tests for BaseAgent.call_tool() and BaseAgent.agentic_loop()."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_core.capability.types import GateDecision
from ze_core.errors import AgentAbortedError, AgentError, HookAbort, ToolBlockedError
from ze_core.orchestration import agent, clear_registry
from ze_core.orchestration.base_agent import (
    BaseAgent,
    _merge_deps,
    _serialise_result,
    _truncate_messages,
)
from ze_core.orchestration.hooks import (
    BaseHarnessHook,
    LoopEndEvent,
    LoopStartEvent,
    ToolEndEvent,
    ToolStartEvent,
    clear_hooks,
    register_hook,
)
from ze_core.orchestration.tool import ToolAccess, clear_tool_registry, tool
from ze_core.orchestration.types import AbortToken, AgentContext, AgentResult, ToolCall


@pytest.fixture(autouse=True)
def clean():
    clear_registry()
    clear_tool_registry()
    clear_hooks()
    yield
    clear_registry()
    clear_tool_registry()
    clear_hooks()


def _ctx(gate: GateDecision = GateDecision.EXECUTE, model: str | None = None) -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt="hello",
        intent="read",
        gate_decision=gate,
        model=model,
    )


def _agent() -> BaseAgent:
    class _A(BaseAgent):
        name = "test"
        description = "test agent"
        tools = []

        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=self.name, response="ok")

    return _A()


# ── call_tool ────────────────────────────────────────────────────────────────

class TestCallTool:
    async def test_executes_read_tool(self):
        @tool(access=ToolAccess.READ, description="Read something")
        async def my_read(x: str) -> str:
            return f"read:{x}"

        a = _agent()
        a.tools = ["my_read"]
        tc = await a.call_tool("my_read", _ctx(), x="hi")

        assert tc.success is True
        assert tc.result == "read:hi"
        assert tc.tool_name == "my_read"
        assert tc.error is None
        assert tc.is_draft is False

    async def test_executes_write_tool_in_execute_mode(self):
        @tool(access=ToolAccess.WRITE, description="Write something")
        async def my_write(x: str) -> str:
            return f"wrote:{x}"

        a = _agent()
        tc = await a.call_tool("my_write", _ctx(GateDecision.EXECUTE), x="data")

        assert tc.success is True
        assert tc.result == "wrote:data"

    async def test_write_tool_suppressed_in_draft_mode(self):
        @tool(access=ToolAccess.WRITE, description="Write")
        async def draft_write(x: str) -> str:
            return "should not run"

        a = _agent()
        tc = await a.call_tool("draft_write", _ctx(GateDecision.DRAFT), x="data")

        assert tc.success is False
        assert tc.is_draft is True
        assert tc.result is None
        assert "suppressed" in tc.error

    async def test_blocked_gate_raises(self):
        @tool(access=ToolAccess.READ, description="Read")
        async def blocked_read(x: str) -> str:
            return x

        a = _agent()
        with pytest.raises(ToolBlockedError):
            await a.call_tool("blocked_read", _ctx(GateDecision.BLOCKED), x="hi")

    async def test_tool_exception_returns_failed_toolcall(self):
        @tool(access=ToolAccess.READ, description="Failing tool")
        async def bad_tool(x: str) -> str:
            raise ValueError("oops")

        a = _agent()
        tc = await a.call_tool("bad_tool", _ctx(), x="hi")

        assert tc.success is False
        assert tc.error == "oops"
        assert tc.result is None
        assert tc.duration_ms >= 0

    async def test_read_tool_suppressed_does_not_suppress(self):
        @tool(access=ToolAccess.READ, description="Read in draft")
        async def read_draft(x: str) -> str:
            return f"got:{x}"

        a = _agent()
        tc = await a.call_tool("read_draft", _ctx(GateDecision.DRAFT), x="q")
        assert tc.success is True

    async def test_unknown_tool_raises(self):
        from ze_core.errors import UnknownToolError
        a = _agent()
        with pytest.raises(UnknownToolError):
            await a.call_tool("does_not_exist", _ctx())


# ── call_tool hooks ───────────────────────────────────────────────────────────

class TestCallToolHooks:
    async def test_on_tool_start_and_end_fire(self):
        events = []

        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                events.append(("start", e.tool_name, e.iteration))
            async def on_tool_end(self, e: ToolEndEvent):
                events.append(("end", e.tool_name, e.tool_call.success))

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def h_tool(x: str) -> str:
            return x

        tc = await _agent().call_tool("h_tool", _ctx(), x="v")

        assert tc.success is True
        assert events == [("start", "h_tool", -1), ("end", "h_tool", True)]

    async def test_on_tool_start_modified_args_used(self):
        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                return {**e.args, "x": "modified"}

        register_hook(_H())

        captured = {}

        @tool(access=ToolAccess.READ, description="t")
        async def capture_tool(x: str) -> str:
            captured["x"] = x
            return x

        await _agent().call_tool("capture_tool", _ctx(), x="original")

        assert captured["x"] == "modified"

    async def test_hook_abort_skips_tool(self):
        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                raise HookAbort(e.tool_name, "quota exceeded")

        register_hook(_H())
        called = []

        @tool(access=ToolAccess.READ, description="t")
        async def skip_me(x: str) -> str:
            called.append(x)
            return x

        tc = await _agent().call_tool("skip_me", _ctx(), x="v")

        assert tc.success is False
        assert "skipped" in tc.error
        assert "quota exceeded" in tc.error
        assert called == []

    async def test_on_tool_end_fires_on_tool_error(self):
        end_events = []

        class _H(BaseHarnessHook):
            async def on_tool_end(self, e: ToolEndEvent):
                end_events.append(e.tool_call.success)

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def fail_tool(x: str) -> str:
            raise RuntimeError("boom")

        tc = await _agent().call_tool("fail_tool", _ctx(), x="v")

        assert tc.success is False
        assert end_events == [False]

    async def test_non_hook_abort_exception_from_start_is_swallowed(self):
        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                raise ValueError("internal hook error")

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def still_runs(x: str) -> str:
            return f"ok:{x}"

        tc = await _agent().call_tool("still_runs", _ctx(), x="hi")
        assert tc.success is True
        assert tc.result == "ok:hi"

    async def test_non_hook_abort_exception_from_end_is_swallowed(self):
        class _H(BaseHarnessHook):
            async def on_tool_end(self, e: ToolEndEvent):
                raise ValueError("hook crash")

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def normal_tool(x: str) -> str:
            return x

        tc = await _agent().call_tool("normal_tool", _ctx(), x="hi")
        assert tc.success is True

    async def test_hooks_do_not_fire_for_blocked_gate(self):
        events = []

        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                events.append("start")

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def blocked_tool(x: str) -> str:
            return x

        with pytest.raises(ToolBlockedError):
            await _agent().call_tool("blocked_tool", _ctx(GateDecision.BLOCKED), x="hi")

        assert events == []

    async def test_hooks_do_not_fire_for_draft_suppressed_write(self):
        events = []

        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                events.append("start")

        register_hook(_H())

        @tool(access=ToolAccess.WRITE, description="t")
        async def draft_write_tool(x: str) -> str:
            return x

        tc = await _agent().call_tool("draft_write_tool", _ctx(GateDecision.DRAFT), x="v")
        assert tc.is_draft is True
        assert events == []

    async def test_iteration_passed_to_events(self):
        iterations = []

        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                iterations.append(e.iteration)

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def iter_tool(x: str) -> str:
            return x

        await _agent().call_tool("iter_tool", _ctx(), _iteration=3, x="v")
        assert iterations == [3]


# ── agentic_loop ─────────────────────────────────────────────────────────────

class TestAgenticLoop:
    def _client(self, responses: list) -> MagicMock:
        """Build a mock client whose complete_with_tools returns each response in turn."""
        client = MagicMock()
        client.complete_with_tools = AsyncMock(side_effect=responses)
        client.complete = AsyncMock(return_value="fallback text")
        return client

    async def test_text_response_terminates_loop(self):
        @tool(access=ToolAccess.READ, description="do X")
        async def noop_tool(q: str) -> str:
            return "result"

        a = _agent()
        a.tools = ["noop_tool"]
        client = self._client([("final answer", None)])
        messages = [{"role": "user", "content": "hi"}]

        text, calls = await a.agentic_loop(_ctx(), client, messages, system="sys")

        assert text == "final answer"
        assert calls == []
        client.complete_with_tools.assert_awaited_once()

    async def test_single_tool_call_then_text(self):
        @tool(access=ToolAccess.READ, description="lookup")
        async def lookup(q: str) -> str:
            return "lookup result"

        a = _agent()
        a.tools = ["lookup"]
        client = self._client([
            (None, [{"id": "c1", "name": "lookup", "arguments": {"q": "hello"}}]),
            ("done", None),
        ])
        messages = [{"role": "user", "content": "search"}]

        text, calls = await a.agentic_loop(_ctx(), client, messages, system="sys")

        assert text == "done"
        assert len(calls) == 1
        assert calls[0].tool_name == "lookup"
        assert calls[0].success is True

    async def test_uses_ctx_model_over_class_model(self):
        @tool(access=ToolAccess.READ, description="t")
        async def t_tool(x: str) -> str:
            return x

        a = _agent()
        a.model = "big-model"
        a.tools = ["t_tool"]
        client = self._client([("done", None)])
        messages = [{"role": "user", "content": "q"}]

        await a.agentic_loop(_ctx(model="small-model"), client, messages, system="s")

        call_kwargs = client.complete_with_tools.call_args[1]
        assert call_kwargs["model"] == "small-model"

    async def test_max_iterations_falls_back_to_plain_complete(self):
        @tool(access=ToolAccess.READ, description="t")
        async def always_calls(x: str) -> str:
            return "r"

        a = _agent()
        a.tools = ["always_calls"]
        tool_response = (None, [{"id": "c1", "name": "always_calls", "arguments": {"x": "v"}}])
        client = self._client([tool_response] * 3)
        messages = [{"role": "user", "content": "q"}]

        text, calls = await a.agentic_loop(
            _ctx(), client, messages, system="s", max_iterations=3
        )

        assert text == "fallback text"
        assert len(calls) == 3
        client.complete.assert_awaited_once()

    async def test_deps_injected_into_tool(self):
        captured = {}

        @tool(access=ToolAccess.READ, description="dep tool")
        async def dep_tool(q: str, db: object) -> str:
            captured["db"] = db
            return "ok"

        fake_db = object()
        a = _agent()
        a.tools = ["dep_tool"]
        client = self._client([
            (None, [{"id": "c1", "name": "dep_tool", "arguments": {"q": "hi"}}]),
            ("done", None),
        ])
        messages = [{"role": "user", "content": "x"}]

        await a.agentic_loop(
            _ctx(), client, messages, system="s", deps={"db": fake_db}
        )

        assert captured["db"] is fake_db

    async def test_no_text_no_tool_calls_raises(self):
        @tool(access=ToolAccess.READ, description="t")
        async def t2(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["t2"]
        client = self._client([(None, None)])
        messages = [{"role": "user", "content": "q"}]

        with pytest.raises(AgentError):
            await a.agentic_loop(_ctx(), client, messages, system="s")

    async def test_multiple_tool_calls_in_one_round(self):
        @tool(access=ToolAccess.READ, description="t")
        async def tool_a(x: str) -> str:
            return f"a:{x}"

        @tool(access=ToolAccess.READ, description="t")
        async def tool_b(x: str) -> str:
            return f"b:{x}"

        a = _agent()
        a.tools = ["tool_a", "tool_b"]
        client = self._client([
            (None, [
                {"id": "c1", "name": "tool_a", "arguments": {"x": "1"}},
                {"id": "c2", "name": "tool_b", "arguments": {"x": "2"}},
            ]),
            ("done", None),
        ])
        messages = [{"role": "user", "content": "q"}]

        text, calls = await a.agentic_loop(_ctx(), client, messages, system="s")

        assert text == "done"
        assert len(calls) == 2
        assert calls[0].tool_name == "tool_a"
        assert calls[1].tool_name == "tool_b"


# ── agentic_loop hooks ────────────────────────────────────────────────────────

class TestAgenticLoopHooks:
    def _client(self, responses):
        client = MagicMock()
        client.complete_with_tools = AsyncMock(side_effect=responses)
        client.complete = AsyncMock(return_value="fallback")
        return client

    async def test_on_loop_start_and_end_fire(self):
        events = []

        class _H(BaseHarnessHook):
            async def on_loop_start(self, e: LoopStartEvent):
                events.append(("start", e.agent_name))
            async def on_loop_end(self, e: LoopEndEvent):
                events.append(("end", e.iterations_used, len(e.tool_calls)))

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def lh_tool(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["lh_tool"]
        client = self._client([("answer", None)])
        await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s")

        assert events == [("start", "test"), ("end", 1, 0)]

    async def test_on_loop_end_receives_tool_calls(self):
        captured = {}

        class _H(BaseHarnessHook):
            async def on_loop_end(self, e: LoopEndEvent):
                captured["calls"] = e.tool_calls
                captured["iterations"] = e.iterations_used

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def le_tool(x: str) -> str:
            return f"r:{x}"

        a = _agent()
        a.tools = ["le_tool"]
        client = self._client([
            (None, [{"id": "c1", "name": "le_tool", "arguments": {"x": "v"}}]),
            ("done", None),
        ])
        await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s")

        assert len(captured["calls"]) == 1
        assert captured["calls"][0].tool_name == "le_tool"
        assert captured["iterations"] == 2

    async def test_on_loop_end_fires_on_max_iterations(self):
        events = []

        class _H(BaseHarnessHook):
            async def on_loop_end(self, e: LoopEndEvent):
                events.append(e.iterations_used)

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def mi_tool(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["mi_tool"]
        tool_resp = (None, [{"id": "c1", "name": "mi_tool", "arguments": {"x": "v"}}])
        client = self._client([tool_resp] * 2)
        await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s", max_iterations=2)

        assert events == [2]

    async def test_on_loop_start_abort_prevents_execution(self):
        class _H(BaseHarnessHook):
            async def on_loop_start(self, e: LoopStartEvent):
                raise AgentAbortedError("rate limited")

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def never_runs(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["never_runs"]
        client = self._client([("answer", None)])

        with pytest.raises(AgentAbortedError, match="rate limited"):
            await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s")

        client.complete_with_tools.assert_not_awaited()

    async def test_abort_token_stops_loop_between_iterations(self):
        token = AbortToken()
        call_count = 0

        @tool(access=ToolAccess.READ, description="t")
        async def count_tool(x: str) -> str:
            nonlocal call_count
            call_count += 1
            token.abort("user cancelled")
            return x

        a = _agent()
        a.tools = ["count_tool"]
        client = self._client([
            (None, [{"id": "c1", "name": "count_tool", "arguments": {"x": "v"}}]),
            (None, [{"id": "c2", "name": "count_tool", "arguments": {"x": "v"}}]),
            ("done", None),
        ])

        ctx = _ctx()
        ctx.abort_token = token

        with pytest.raises(AgentAbortedError, match="user cancelled"):
            await a.agentic_loop(ctx, client, [{"role": "user", "content": "q"}], system="s")

        assert call_count == 1  # second iteration never runs

    async def test_loop_hook_exception_does_not_abort(self):
        class _H(BaseHarnessHook):
            async def on_loop_start(self, e: LoopStartEvent):
                raise ValueError("hook crash")

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def safe_tool(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["safe_tool"]
        client = self._client([("answer", None)])
        text, _ = await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s")

        assert text == "answer"

    async def test_iteration_index_passed_to_tool_hooks(self):
        iterations_seen = []

        class _H(BaseHarnessHook):
            async def on_tool_start(self, e: ToolStartEvent):
                iterations_seen.append(e.iteration)

        register_hook(_H())

        @tool(access=ToolAccess.READ, description="t")
        async def idx_tool(x: str) -> str:
            return x

        a = _agent()
        a.tools = ["idx_tool"]
        client = self._client([
            (None, [{"id": "c1", "name": "idx_tool", "arguments": {"x": "v"}}]),
            (None, [{"id": "c2", "name": "idx_tool", "arguments": {"x": "v"}}]),
            ("done", None),
        ])
        await a.agentic_loop(_ctx(), client, [{"role": "user", "content": "q"}], system="s")

        assert iterations_seen == [0, 1]


# ── _merge_deps ───────────────────────────────────────────────────────────────

class TestMergeDeps:
    def test_injects_missing_dep(self):
        @tool(access=ToolAccess.READ, description="t")
        async def with_dep(q: str, client: object) -> str:
            return q

        fake = object()
        merged = _merge_deps("with_dep", {"q": "hello"}, {"client": fake})
        assert merged["client"] is fake
        assert merged["q"] == "hello"

    def test_llm_args_take_precedence(self):
        @tool(access=ToolAccess.READ, description="t")
        async def override_tool(x: str) -> str:
            return x

        result = _merge_deps("override_tool", {"x": "llm"}, {"x": "dep"})
        assert result["x"] == "llm"

    def test_extra_deps_not_in_signature_are_ignored(self):
        @tool(access=ToolAccess.READ, description="t")
        async def simple(x: str) -> str:
            return x

        result = _merge_deps("simple", {"x": "v"}, {"unknown_dep": "should_not_appear"})
        assert "unknown_dep" not in result


# ── _serialise_result ────────────────────────────────────────────────────────

class TestSerialiseResult:
    def _tc(self, **kwargs) -> ToolCall:
        defaults = dict(tool_name="t", args={}, result=None, duration_ms=0, success=True)
        defaults.update(kwargs)
        return ToolCall(**defaults)

    def test_failed_returns_error_string(self):
        tc = self._tc(success=False, error="boom", result=None)
        assert _serialise_result(tc) == "[error: boom]"

    def test_none_result(self):
        tc = self._tc(result=None)
        assert _serialise_result(tc) == "[no result]"

    def test_string_result(self):
        tc = self._tc(result="hello world")
        assert _serialise_result(tc) == "hello world"

    def test_dict_result_json(self):
        tc = self._tc(result={"key": "val"})
        assert _serialise_result(tc) == '{"key": "val"}'

    def test_non_serialisable_falls_back_to_str(self):
        class _NS:
            def __repr__(self):
                return "NS()"

        tc = self._tc(result=_NS())
        assert "NS()" in _serialise_result(tc)


# ── _truncate_messages ────────────────────────────────────────────────────────

class TestTruncateMessages:
    def _msg(self, role: str, content: str = "x") -> dict:
        return {"role": role, "content": content}

    def _tool_round(self, call_id: str = "c1") -> list[dict]:
        return [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": call_id, "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": call_id, "content": "result"},
        ]

    def test_no_truncation_when_under_budget(self):
        messages = [self._msg("user")]
        _truncate_messages(messages, max_tokens=10000)
        assert len(messages) == 1

    def test_removes_oldest_tool_round(self):
        messages = [
            *self._tool_round("c1"),
            *self._tool_round("c2"),
            self._msg("user", "final"),
        ]
        # Each message is ~60 chars → ~15 tokens. Force truncation with budget=30 tokens.
        _truncate_messages(messages, max_tokens=30)
        # The oldest round (c1 assistant + c1 tool) should be removed.
        ids = [m.get("tool_call_id") for m in messages if m.get("role") == "tool"]
        assert "c1" not in ids

    def test_last_4_messages_never_removed(self):
        # Only last 4 messages exist — budget is tiny → nothing removed.
        messages = [*self._tool_round("c1"), self._msg("user")]
        original_len = len(messages)
        _truncate_messages(messages, max_tokens=1)
        assert len(messages) == original_len


# ── _fetch_tool_executor_context / ToolExecutorPolicy ─────────────────────────

class TestToolExecutorContextFetch:
    """agentic_loop prepends memory context to system when ctx.memory_store is set."""

    def _make_ctx_with_memory(self, memory_store=None):
        ctx = AgentContext(
            session_id="s1",
            prompt="Do the task",
            intent="execute",
            gate_decision=GateDecision.EXECUTE,
        )
        ctx.memory_store = memory_store
        return ctx

    async def test_no_prepend_when_memory_store_is_none(self):
        a = _agent()
        client = AsyncMock()
        client.complete_with_tools = AsyncMock(return_value=("done", None))

        captured_systems = []

        async def _capture(**kwargs):
            captured_systems.append(kwargs.get("system", ""))
            return "done", None

        client.complete_with_tools = _capture

        ctx = self._make_ctx_with_memory(memory_store=None)
        await a.agentic_loop(ctx, client, [{"role": "user", "content": "hi"}], system="BASE")

        assert captured_systems[0] == "BASE"

    async def test_prepends_facts_when_memory_store_set(self):
        from ze_memory.types import Fact, MemoryContext

        a = _agent()

        memory_ctx = MemoryContext(
            facts=[Fact(predicate="preferred_language", value="Python", confidence=1.0)],
        )
        memory_store = AsyncMock()
        memory_store.retrieve = AsyncMock(return_value=memory_ctx)

        captured_systems = []

        async def _capture(**kwargs):
            captured_systems.append(kwargs.get("system", ""))
            return "done", None

        client = AsyncMock()
        client.complete_with_tools = _capture

        ctx = self._make_ctx_with_memory(memory_store=memory_store)

        with patch("ze_core.embeddings.get_embedder") as mock_embedder:
            mock_embedder.return_value.encode = MagicMock(return_value=[0.1] * 384)
            await a.agentic_loop(ctx, client, [{"role": "user", "content": "hi"}], system="BASE")

        assert len(captured_systems) > 0
        assert "preferred_language" in captured_systems[0] or "Relevant facts" in captured_systems[0]

    async def test_memory_store_failure_does_not_abort_loop(self):
        a = _agent()

        memory_store = AsyncMock()
        memory_store.retrieve = AsyncMock(side_effect=RuntimeError("DB down"))

        client = AsyncMock()
        client.complete_with_tools = AsyncMock(return_value=("done", None))

        ctx = self._make_ctx_with_memory(memory_store=memory_store)

        with patch("ze_core.embeddings.get_embedder") as mock_embedder:
            mock_embedder.return_value.encode = MagicMock(return_value=[0.1] * 384)
            result, _ = await a.agentic_loop(ctx, client, [{"role": "user", "content": "hi"}], system="BASE")

        assert result == "done"
