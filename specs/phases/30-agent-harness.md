# Agent Harness — Spec

> **Package:** `ze_core`
> **Phase:** 21
> **Status:** Pending

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `HarnessHook` protocol + event types | ✅ Done |
| `HookRegistry` — global singleton | ✅ Done |
| Hook dispatch in `call_tool` | 🔲 Pending |
| Hook dispatch in `agentic_loop` | 🔲 Pending |
| `AbortToken` type | 🔲 Pending |
| `AbortToken` wired into `AgentContext` | 🔲 Pending |
| Abort check per loop iteration | 🔲 Pending |
| `Container.abort_invocation()` | 🔲 Pending |
| `delegate_to_agent` tool | 🔲 Pending |
| Delegate dep injection in `agentic_loop` | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

`BaseAgent` currently executes tool calls and agentic loops without any external
extension points. Adding a cross-cutting concern — cost enforcement, audit logging,
rate limiting, per-tool circuit breakers — requires modifying `BaseAgent` or every
agent's `run()` method.

This phase introduces three coordinated harness capabilities:

1. **Hook points** — `before_tool` / `after_tool` / loop lifecycle callbacks that
   cross-cutting concerns can register without touching agent code.
2. **Step-level abort** — an `AbortToken` that external code (cost reconciler, user
   cancel, time-budget hook) can fire to cleanly stop a loop mid-execution.
3. **Multi-agent handoffs** — a `delegate_to_agent` tool that lets the LLM route a
   sub-task to a specialised agent and fold the result back into the current loop.

---

## Responsibilities

- Define `HarnessHook` protocol and per-event dataclasses.
- Maintain a global `HookRegistry`; dispatch hooks from `call_tool` and `agentic_loop`.
- Allow hooks to modify tool args (`on_tool_start` return value) or abort a single
  tool call (raise `HookAbort`).
- Provide `AbortToken` — a lightweight async event with a reason string — and check
  it at the start of every loop iteration.
- Expose `Container.abort_invocation(thread_id)` so external code can abort a
  running graph.
- Implement `delegate_to_agent` as a ze_core-registered tool; agents opt in by
  adding `"delegate_to_agent"` to `self.tools`.

---

## Out of Scope

- Changing graph-level routing (EmbeddingRouter, `execute_tool` node).
- Modifying the LangGraph checkpoint or `AgentState` structure.
- Streaming support for delegated agents — delegation returns the full result.
- Parallel delegation (one delegate call at a time within a single loop).
- Hook persistence — hooks are in-process; they are not stored or replayed.

---

## Module Location

```
packages/ze-core/
  ze_core/
    orchestration/
      hooks.py          # HarnessHook, event types, HookRegistry
      delegate.py       # delegate_to_agent tool
      base_agent.py     # hook dispatch + abort check (modified)
      types.py          # AbortToken added to AgentContext (modified)
    errors.py           # AgentAbortedError, HookAbort added (modified)
    container.py        # abort_invocation() added (modified)
```

---

## Interface Contract

### Hooks

```python
# ze_core/orchestration/hooks.py

@dataclass
class ToolStartEvent:
    tool_name: str
    args: dict[str, Any]
    ctx: AgentContext
    iteration: int          # which agentic_loop iteration (0-indexed); -1 for direct call_tool

@dataclass
class ToolEndEvent:
    tool_name: str
    tool_call: ToolCall     # includes success, duration_ms, result/error
    ctx: AgentContext
    iteration: int

@dataclass
class LoopStartEvent:
    agent_name: str
    ctx: AgentContext

@dataclass
class LoopEndEvent:
    agent_name: str
    ctx: AgentContext
    tool_calls: list[ToolCall]
    iterations_used: int


class HarnessHook(Protocol):
    """All methods have default no-op implementations; override only what you need."""

    async def on_tool_start(self, event: ToolStartEvent) -> dict[str, Any] | None:
        """Called before a tool executes.

        Return a modified args dict to replace the original args.
        Return None to use args unchanged.
        Raise HookAbort to skip this tool call entirely.
        """
        ...

    async def on_tool_end(self, event: ToolEndEvent) -> None:
        """Called after a tool executes (success or error). Cannot modify the result."""
        ...

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        """Called once when agentic_loop begins."""
        ...

    async def on_loop_end(self, event: LoopEndEvent) -> None:
        """Called once when agentic_loop returns (text response or max iterations)."""
        ...


def register_hook(hook: HarnessHook) -> None: ...
def get_hooks() -> list[HarnessHook]: ...
```

### Abort Token

```python
# ze_core/orchestration/types.py  (additions)

@dataclass
class AbortToken:
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str | None = None

    def abort(self, reason: str | None = None) -> None:
        """Signal the running loop to stop after the current tool call."""
        self.reason = reason
        self._event.set()

    @property
    def is_set(self) -> bool:
        return self._event.is_set()


@dataclass
class AgentContext:
    ...
    abort_token: AbortToken | None = field(default=None, repr=False)  # NEW
```

### Container abort

```python
# ze_core/container.py  (addition)

async def abort_invocation(self, thread_id: str, reason: str | None = None) -> None:
    """Signal the agentic loop running under thread_id to stop cleanly.

    No-op if the thread has no active AbortToken (e.g. graph already completed).
    """
```

### Errors

```python
# ze_core/errors.py  (additions)

class AgentAbortedError(ZeError):
    """Raised inside agentic_loop when AbortToken fires."""
    def __init__(self, reason: str | None = None): ...

class HookAbort(ZeError):
    """Raised from HarnessHook.on_tool_start to skip a single tool call.

    The loop records the skipped call and continues to the next LLM turn.
    """
    def __init__(self, tool_name: str, reason: str = ""): ...
```

### Delegate tool

```python
# ze_core/orchestration/delegate.py

@tool("delegate_to_agent", access="read")
async def delegate_to_agent(
    agent_name: str,
    task: str,
    context: str | None = None,
    *,
    _parent_ctx: AgentContext,      # injected via deps; never LLM-visible
    _get_agent: Callable,           # injected via deps; never LLM-visible
) -> str:
    """Delegate a subtask to a specialised agent and return its complete response.

    Use when the current task is better handled by a different agent —
    for example, delegating calendar lookups to the calendar agent while
    the research agent focuses on web search.
    """
```

---

## Data Structures

```python
# ze_core/orchestration/hooks.py

@dataclass
class ToolStartEvent:
    tool_name: str
    args: dict[str, Any]
    ctx: AgentContext
    iteration: int

@dataclass
class ToolEndEvent:
    tool_name: str
    tool_call: ToolCall
    ctx: AgentContext
    iteration: int

@dataclass
class LoopStartEvent:
    agent_name: str
    ctx: AgentContext

@dataclass
class LoopEndEvent:
    agent_name: str
    ctx: AgentContext
    tool_calls: list[ToolCall]
    iterations_used: int
```

---

## Behaviour Details

### Hook dispatch in `call_tool`

```python
async def call_tool(self, name: str, ctx: AgentContext, **kwargs) -> ToolCall:
    hooks = get_hooks()

    # before
    args = kwargs
    for hook in hooks:
        try:
            modified = await hook.on_tool_start(ToolStartEvent(name, args, ctx, iteration=-1))
            if modified is not None:
                args = modified
        except HookAbort as e:
            log.info("tool_skipped_by_hook", tool=name, reason=str(e))
            return ToolCall(tool_name=name, args=args, result=None, duration_ms=0,
                            success=False, error=f"skipped: {e.reason}")

    # execute (existing logic, using args instead of kwargs)
    tool_call = await _dispatch(name, ctx, **args)

    # after
    for hook in hooks:
        await hook.on_tool_end(ToolEndEvent(name, tool_call, ctx, iteration=-1))

    return tool_call
```

`iteration` is `-1` when `call_tool` is invoked directly (outside a loop). The
loop passes the actual iteration index when calling `call_tool` internally.

### Hook dispatch in `agentic_loop`

`on_loop_start` may raise `AgentAbortedError` directly to prevent the loop from
starting at all — useful for pre-flight checks such as rate limiting or session
quotas. The exception propagates identically to a mid-loop abort. The loop does not
catch it. Hooks that raise anything other than `AgentAbortedError` or `HookAbort`
have their exceptions caught and logged as warnings (same rule as tool hooks).

```python
async def agentic_loop(self, ctx, client, messages, system, ...):
    hooks = get_hooks()
    # on_loop_start may raise AgentAbortedError to abort before the first iteration
    await _dispatch_hooks(hooks, "on_loop_start", LoopStartEvent(self.name, ctx))

    for iteration in range(max_iterations):
        # abort check — start of each iteration
        if ctx.abort_token is not None and ctx.abort_token.is_set:
            raise AgentAbortedError(ctx.abort_token.reason)

        text, tool_calls = await client.complete_with_tools(...)

        if text:
            await _dispatch_hooks(hooks, "on_loop_end",
                LoopEndEvent(self.name, ctx, accumulated, iterations_used=iteration+1))
            return text, accumulated

        for tc in tool_calls:
            # pass iteration index into call_tool so ToolStartEvent has it
            tool_call = await self._call_tool_in_loop(tc, ctx, deps, iteration)
            accumulated.append(tool_call)
            messages.append(...)

    # max iterations hit — same loop_end dispatch
    await _dispatch_hooks(hooks, "on_loop_end",
        LoopEndEvent(self.name, ctx, accumulated, iterations_used=max_iterations))
    ...
```

### Abort token lifecycle

1. `Container.invoke()` creates an `AbortToken` and stores it in a `dict[str, AbortToken]`
   keyed by `thread_id`.
2. The token is placed on `AgentContext` before passing to the graph.
3. On graph completion, the container removes the token from the dict.
4. `Container.abort_invocation(thread_id)` looks up the token and calls `.abort()`.
   If the thread_id is not found (already done), it is a no-op.

`AgentAbortedError` propagates out of `agentic_loop` and up through the graph's
`execute_tool` node. The `error` field in `AgentState` is set; the final response
is sent as a cancellation acknowledgement ("Got it, stopping.").

### Multi-agent handoffs

Agents opt in by adding `"delegate_to_agent"` to their `tools` class attribute:

```python
class ResearchAgent(BaseAgent):
    tools = ["web_search", "delegate_to_agent"]
```

`agentic_loop` always adds `_parent_ctx`, `_get_agent`, and `_depth` to the `deps` dict
(never LLM-visible — excluded by `llm_schema()` because their types are not JSON-primitive).

`delegate_to_agent` implementation:

```python
_DELEGATE_MAX_DEPTH = 2

async def delegate_to_agent(
    agent_name: str,
    task: str,
    context: str | None = None,
    *,
    _parent_ctx: AgentContext,
    _get_agent: Callable[[str], BaseAgent],
    _depth: int = 0,
) -> str:
    if _depth >= _DELEGATE_MAX_DEPTH:
        raise ZeError(f"delegation depth limit exceeded (max {_DELEGATE_MAX_DEPTH})")

    agent = _get_agent(agent_name)
    if agent is None:
        raise ZeError(f"Unknown agent: {agent_name!r}")

    sub_ctx = AgentContext(
        session_id=_parent_ctx.session_id,
        prompt=task if context is None else f"{context}\n\n{task}",
        intent=agent_name,
        gate_decision=_parent_ctx.gate_decision,
        memory=_parent_ctx.memory,
        contacts=_parent_ctx.contacts,
        persona=_parent_ctx.persona,
        model=None,                     # delegated agent uses its own default
        messages=[{"role": "user", "content": task}],
        reporter=_parent_ctx.reporter,
        identity_builder=_parent_ctx.identity_builder,
        abort_token=_parent_ctx.abort_token,    # propagate abort signal
    )
    # Sub-agent's agentic_loop will receive _depth + 1 so the cap is enforced
    # transitively through all delegation levels.
    result = await agent.run(sub_ctx, _delegate_depth=_depth + 1)
    return result.response
```

`BaseAgent.run()` accepts an optional `_delegate_depth: int = 0` kwarg and passes it
into `agentic_loop` via `deps["_depth"]`. Agents that do not use `delegate_to_agent`
ignore it entirely.

The delegated agent's `tool_calls` are NOT merged into the parent's `accumulated` list.
Only the text response is returned. This keeps the parent loop's tool call record clean.

---

## Example: cost-cap hook

```python
# ze/hooks/cost_cap.py

class CostCapHook:
    def __init__(self, max_tool_calls: int = 10):
        self._max = max_tool_calls
        self._counts: dict[str, int] = {}   # session_id → count

    async def on_tool_end(self, event: ToolEndEvent) -> None:
        sid = event.ctx.session_id
        self._counts[sid] = self._counts.get(sid, 0) + 1
        if self._counts[sid] >= self._max:
            if event.ctx.abort_token is not None:
                event.ctx.abort_token.abort("tool_call_limit_exceeded")
```

Wired at startup:

```python
# ze/container.py
from ze_core.orchestration.hooks import register_hook
register_hook(CostCapHook(max_tool_calls=settings.max_tool_calls_per_turn))
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.orchestration.tool` | `get_tool`, `@tool` for delegate registration |
| `ze_core.orchestration.registry` | `get_agent` for delegate dispatch |
| `ze_core.errors` | `AgentAbortedError`, `HookAbort` |
| `ze_core.orchestration.types` | `AgentContext`, `ToolCall`, `AbortToken` |

---

## Implementation Notes

- `HarnessHook` is a `Protocol`, not an ABC, so hooks don't need to implement all
  methods — the default no-op implementations are provided via a mixin base class
  `BaseHarnessHook` that users can optionally inherit from.
- `AbortToken` wraps `asyncio.Event` rather than a plain bool so future code could
  `await` the token if needed (e.g. "wait for completion or abort").
- Delegate depth is hard-capped at 2 levels. `agentic_loop` always injects `_depth: int`
  into deps (starting at 0 for the top-level call, incremented by `delegate_to_agent`
  before running the sub-agent). If `_depth >= 2`, `delegate_to_agent` raises
  `ZeError("delegation depth limit exceeded")` before running the sub-agent. This cap
  is intentionally not configurable; if deeper chains are ever needed, the spec should
  be revisited explicitly rather than silently bumped via config.
- Hooks self-filter by agent using `event.ctx.intent` — no per-agent hook registration
  is needed. The `HookRegistry` is global-only.
- Hook exceptions (other than `HookAbort`) are caught and logged as warnings; they
  do not abort the tool call. Hooks must not raise to signal non-abort errors.
- `delegate_to_agent` inherits the parent's `abort_token` so a top-level abort
  propagates through the delegation chain.

---

## Open Questions

- [x] Should `HookRegistry` support per-agent hooks? **No — global-only.** All event
  types carry `AgentContext` (with `intent` = agent name) so hooks self-filter.
  Per-agent registration would add indirection for no benefit.
- [x] Should delegate depth be bounded? **Yes — hard cap of 2 levels.** Enforced via
  `_depth` counter in deps; raises `ZeError` at `_depth >= 2`. Not configurable.
  See the delegate implementation block above.
- [x] Should `on_loop_start` be able to abort before the first iteration? **Yes.**
  Hooks may raise `AgentAbortedError` directly from `on_loop_start`. The loop does
  not catch it; it propagates the same way as a mid-loop abort. Documented in the
  hook dispatch section above.
