# Agent & Tool API — Spec

## Purpose

Define a first-class, declarative API for authoring agents and tools in Ze.
Replace the current pattern of manually-wired constructors, copy-pasted config
helpers, and documentation-only tool lists with a system where:

- Tools are registered objects with declared access levels and parameter schemas.
- Agents declare their tool dependencies as a class attribute, validated at startup.
- Capability enforcement moves from a pre-execution gate check into every tool
  call, transparently suppressing write tools in draft mode.
- Bootstrap auto-wires agent constructors from a type-keyed dependency map,
  eliminating per-agent wiring code.
- Lifecycle hooks let agents warm up and clean up without touching app startup.

This spec supersedes the tool and registry sections of `04-agents.md` and
extends (but does not replace) `02-capability-gate.md`.

---

## What Changes and Why

| Area | Before | After |
|---|---|---|
| Tool registry | YAML `tools:` list — documentation only | `@tool` decorator — runtime registry with access level |
| Capability enforcement | One gate check before agent runs (routing intent) | Gate check + per-tool enforcement in `call_tool()` |
| Draft mode | No structural enforcement — write tools can fire | Write-access tools return `DraftToolCall`, no side effects |
| Config helpers | `_model()`, `_timeout()`, memory formatting copy-pasted per agent | Implemented once on `BaseAgent` |
| `AgentContext` | No `gate_decision` field | Carries `gate_decision` — agents and tools can read it |
| Bootstrap | Manually lists each agent class with positional dep tuple | Generic type-keyed DI — new agents wire themselves |
| Startup | No cross-checks between declared tools and registry | Fails hard if declared tool is unregistered or intent is missing from capabilities |
| Lifecycle | No hooks | `startup()` / `shutdown()` on `BaseAgent` |

---

## Tool API

### `ze/agents/tool.py`

#### `ToolAccess` — declared risk level of a tool

```python
from enum import Enum

class ToolAccess(str, Enum):
    READ  = "read"   # safe in any gate decision, including DRAFT
    WRITE = "write"  # suppressed when gate_decision is GateDecision.DRAFT
```

`READ` covers all retrieval operations (web search, calendar read, email read).
`WRITE` covers all operations with external side effects (send email, create event,
run script, move file). When in doubt, use `WRITE`.

#### `ToolSpec` — registered metadata for a tool

```python
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

@dataclass(frozen=True)
class ToolParam:
    name:       str
    annotation: type
    required:   bool
    default:    Any = None

@dataclass(frozen=True)
class ToolSpec:
    name:        str
    fn:          Callable[..., Awaitable["ToolCall"]]
    access:      ToolAccess
    description: str
    params:      tuple[ToolParam, ...]
```

`params` is derived from the tool function's type annotations at decoration time
using `inspect.signature`. This gives the system a machine-readable parameter
schema without requiring a separate declaration.

#### `@tool` decorator

```python
def tool(*, access: ToolAccess | str, description: str) -> Callable:
    """Register an async function as a Ze tool.

    Args:
        access:      ToolAccess.READ or ToolAccess.WRITE
        description: One sentence — used in log output and future LLM tool schemas
    """
```

**Usage:**

```python
from ze.agents.tool import tool, ToolAccess
from ze.agents.types import ToolCall

@tool(access=ToolAccess.READ, description="Search the web for current information.")
async def web_search(query: str, client: AsyncTavilyClient, max_results: int = 5) -> ToolCall:
    ...

@tool(access=ToolAccess.WRITE, description="Send an email via Gmail.")
async def send_email(to: str, subject: str, body: str, client: GmailClient) -> ToolCall:
    ...
```

The decorator registers the tool in a module-level dict (`_tool_registry`) keyed
by function name. It does not alter the function — calling `web_search(...)` directly
still works (used in tests). Registration happens when the module is imported;
`ze/agents/<name>/tools.py` must be imported at startup for the agent's tools to appear.

#### Registry accessors

```python
def get_tool(name: str) -> ToolSpec:
    """Raises UnknownToolError if the tool is not registered."""

def registered_tools() -> dict[str, ToolSpec]:
    """Return a snapshot of the full tool registry."""
```

---

## Updated `BaseAgent`

### `ze/agents/base.py`

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ze.agents.types import AgentContext, AgentResult
from ze.capability.types import GateDecision
from ze.errors import ToolBlockedError
from ze.logging import get_logger
from ze.settings import Settings


class BaseAgent(ABC):
    name: str           # set by subclass as a class attribute
    tools: list[str] = []  # names of tools this agent may call

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._log = get_logger(__name__)

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult: ...

    @abstractmethod
    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]: ...

    # ── Lifecycle (optional override) ─────────────────────────────────────────

    async def startup(self) -> None:
        """Called once at app startup, after DI wiring. Override for warmup."""

    async def shutdown(self) -> None:
        """Called during app shutdown. Override for cleanup."""

    # ── Tool execution ────────────────────────────────────────────────────────

    async def call_tool(self, name: str, ctx: AgentContext, **kwargs) -> ToolCall:
        """Execute a registered tool with capability enforcement.

        - WRITE tools are suppressed and return DraftToolCall when gate is DRAFT.
        - All tools raise ToolBlockedError when gate is BLOCKED.
        - Timing and structured logging are applied automatically.
        """
        from ze.agents.tool import get_tool
        spec = get_tool(name)

        if ctx.gate_decision == GateDecision.BLOCKED:
            raise ToolBlockedError(f"Tool {name!r} is blocked by the capability gate")

        if spec.access == ToolAccess.WRITE and ctx.gate_decision == GateDecision.DRAFT:
            self._log.info("tool_suppressed_draft", tool=name, agent=self.name)
            return ToolCall(
                tool_name=name,
                args=kwargs,
                result=None,
                duration_ms=0,
                success=False,
                error="suppressed: draft mode",
                is_draft=True,
            )

        self._log.debug("tool_start", tool=name, agent=self.name, access=spec.access)
        result = await spec.fn(**kwargs)
        self._log.info(
            "tool_complete",
            tool=name,
            agent=self.name,
            success=result.success,
            duration_ms=result.duration_ms,
        )
        return result

    # ── Config helpers ────────────────────────────────────────────────────────

    def _model(self) -> str:
        return self._settings.agent_configs.get(self.name, {}).get(
            "model", "anthropic/claude-sonnet-4-5"
        )

    def _timeout(self) -> int:
        return int(
            self._settings.agent_configs.get(self.name, {}).get("timeout", 30)
        )

    def _format_memory(self, ctx: AgentContext) -> str:
        """Render memory facts as a bullet list for system prompt injection."""
        lines = [f"- {f.key}: {f.value}" for f in ctx.memory.facts]
        return "\n".join(lines) if lines else "(none)"
```

> **Implementation note (current):** Agent `model`, `timeout`, and `intents` are
> `@agent` class attributes on each agent class (`model`, `timeout`, `description`,
> `intents`, `tools`). The YAML `agent_configs` map and `_model()` / `_timeout()`
> helpers shown above were removed in later phases.

### Subclass contract

A minimal agent implementation:

```python
from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from . import tools  # import triggers tool registration
from .prompt import SYSTEM_PROMPT


@register
class ResearchAgent(BaseAgent):
    name  = "research"
    tools = ["web_search"]

    def __init__(self, openrouter_client: OpenRouterClient, tavily_client: AsyncTavilyClient, settings: Settings) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._tavily = tavily_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        tc = await self.call_tool("web_search", ctx, query=ctx.prompt, client=self._tavily)

        augmented = f"{ctx.prompt}\n\nSearch results:\n{format_search_results(tc)}"
        response = await self._client.complete(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(),
            system=SYSTEM_PROMPT.format(memory_context=self._format_memory(ctx)),
        )
        return AgentResult(agent=self.name, response=response, tool_calls=[tc])

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        tc = await self.call_tool("web_search", ctx, query=ctx.prompt, client=self._tavily)
        augmented = f"{ctx.prompt}\n\nSearch results:\n{format_search_results(tc)}"
        async for token in self._client.stream(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(),
            system=SYSTEM_PROMPT.format(memory_context=self._format_memory(ctx)),
        ):
            yield token
```

Key differences from the current pattern:
- No `_model()` / `_timeout()` / memory formatting boilerplate — inherited
- `call_tool()` instead of direct function call — enforcement applied automatically
- `from . import tools` triggers `@tool` registration for this agent's module

---

## Updated Shared Types

### `ze/agents/types.py`

```python
@dataclass
class ToolCall:
    tool_name:   str
    args:        dict[str, Any]
    result:      Any
    duration_ms: int
    success:     bool
    error:       str | None = None
    is_draft:    bool = False     # True when suppressed by draft mode

@dataclass
class AgentContext:
    session_id:    str
    prompt:        str
    intent:        str
    gate_decision: GateDecision                  # new — passed in from orchestration
    memory:        MemoryContext = field(default_factory=MemoryContext)
    tool_calls:    list[ToolCall] = field(default_factory=list)

@dataclass
class AgentResult:
    agent:            str
    response:         str
    tool_calls:       list[ToolCall] = field(default_factory=list)
    tokens_used:      int = 0
    memory_proposals: list = field(default_factory=list)
```

`gate_decision` on `AgentContext` is the single source of truth for enforcement
inside an agent run. It is set by the orchestration layer before invoking the agent
and must never be mutated by the agent.

---

## Bootstrap — Automatic Dependency Wiring

### `ze_agents/bootstrap.py`

Bootstrap maintains a type-keyed dependency map. At startup it populates the map
with all shared singletons, then iterates `_class_registry` to instantiate every
enabled agent by resolving constructor parameters against the map.

```python
from typing import Any, get_type_hints
import inspect

from ze.agents.registry import _class_registry, register_instance
from ze.errors import AgentConfigError

_dep_map: dict[type, Any] = {}


def bootstrap_agents(
    *,
    openrouter_client: OpenRouterClient,
    settings: Settings,
    tavily_client: AsyncTavilyClient | None = None,
) -> None:
    if tavily_client is None:
        tavily_client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    _dep_map[OpenRouterClient]   = openrouter_client
    _dep_map[Settings]           = settings
    _dep_map[AsyncTavilyClient]  = tavily_client

    for name, cls in _class_registry.items():
        agent_cfg = settings.agent_configs.get(name, {})
        if not agent_cfg.get("enabled", True):
            continue
        instance = _resolve(cls)
        register_instance(name, instance)

    validate_registry(settings)


def _resolve(cls: type) -> object:
    """Instantiate cls by matching __init__ parameter types against _dep_map."""
    sig = inspect.signature(cls.__init__)
    hints = get_type_hints(cls.__init__)
    kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        annotation = hints.get(param_name)
        if annotation is None:
            raise AgentConfigError(
                f"{cls.__name__}.__init__ parameter {param_name!r} has no type annotation"
            )
        if annotation not in _dep_map:
            raise AgentConfigError(
                f"No dependency registered for type {annotation!r} "
                f"(required by {cls.__name__})"
            )
        kwargs[param_name] = _dep_map[annotation]

    return cls(**kwargs)
```

> **Implementation note (current):** Agents are enabled/disabled via the `@agent` registry
> and plugin packaging — not a YAML `agent_configs.enabled` flag. `Settings` in production
> is `ze_agents.settings.Settings` (core bridge from `ZeApiSettings.to_core_settings()`).

To add a new agent with standard deps (`OpenRouterClient`, `Settings`), no changes
to `bootstrap.py` are required — the resolver finds them automatically. For agents
with non-standard external clients (e.g., a `GmailClient`), add the singleton to
`_dep_map` before calling `bootstrap_agents()`.

### Registering new dep types

For Phase 3 agents (calendar, email) that need OAuth clients:

```python
# In ze/api/app.py lifespan, before bootstrap_agents():
from ze.agents.bootstrap import _dep_map
_dep_map[GmailClient] = GmailClient(token=settings.gmail_token)
_dep_map[CalendarClient] = CalendarClient(token=settings.calendar_token)
bootstrap_agents(openrouter_client=..., settings=...)
```

---

## Startup Validation

`validate_registry()` runs once at the end of `bootstrap_agents()`. A failure here
aborts startup — misconfigured agents must not silently degrade.

```python
def validate_registry(settings: Settings) -> None:
    from ze.agents.tool import registered_tools
    from ze.agents.registry import _class_registry

    tool_reg = registered_tools()
    capabilities = settings.capabilities_config.get("capabilities", {})

    for agent_name, agent_cls in _class_registry.items():
        declared_tools = getattr(agent_cls, "tools", [])
        agent_cap = capabilities.get(agent_name, {})

        for tool_name in declared_tools:
            # 1. Every declared tool must exist in the tool registry.
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {agent_name!r} declares unknown tool {tool_name!r}. "
                    f"Ensure the tools module is imported in the agent package."
                )

        # 2. Every intent in the agent's intent_map must have a capabilities entry.
        intent_map = settings.agent_configs.get(agent_name, {}).get("intent_map", {})
        for intent in intent_map:
            if intent not in agent_cap:
                raise AgentConfigError(
                    f"{agent_name}.{intent} declared in config intent_map "
                    f"but missing from capabilities.yaml."
                )
```

Checks performed:
1. Every name in `agent.tools` resolves to a registered `ToolSpec`.
2. Every intent key in `config/agents/<name>.yaml:intent_map` has a matching
   entry in `config/capabilities.yaml` for that agent.

---

## Orchestration Integration

The orchestration layer is responsible for building `AgentContext` and must
populate `gate_decision` before the agent runs. No other changes to the graph
flow are required.

### `ze/orchestration/nodes/execution.py`

**`execute_tool` node** — pass `gate_decision` into context:

```python
async def execute_tool(state: AgentState, config: RunnableConfig) -> dict:
    ...
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=state["gate_decision"],   # was missing before
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings, token_queue)
    return {"agent_result": result}
```

**`draft_response` node** — set `gate_decision` to `DRAFT` explicitly:

```python
async def draft_response(state: AgentState, config: RunnableConfig) -> dict:
    ...
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=GateDecision.DRAFT,   # override — suppress write tools
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings)
    return {"agent_result": result, "pending_confirmation": True}
```

`draft_response` no longer needs any special branching or tool suppression logic in
the node itself — that enforcement is transparent inside `call_tool()`. The agent's
`run()` method is identical in both paths; draft suppression is an implementation
detail of the tool layer.

### Graph flow — unchanged

The graph topology does not change. The only difference is that `gate_decision`
flows into `AgentContext` so that `call_tool()` can use it.

```
embed_route → fetch_context → capability_check
                                      │
                          ┌───────────┼───────────────────┐
                          │           │                   │
                       EXECUTE      DRAFT        AWAIT_CONFIRMATION
                          │           │                   │
                    execute_tool  draft_response   await_confirmation
                    (gate=EXECUTE) (gate=DRAFT)
```

---

## Draft Enforcement Semantics

When `ctx.gate_decision == GateDecision.DRAFT`:

| Tool access | Result |
|---|---|
| `ToolAccess.READ` | Executes normally — reads are always allowed |
| `ToolAccess.WRITE` | Returns `ToolCall(success=False, is_draft=True, error="suppressed: draft mode")` |

The agent's `run()` method does not need to check `gate_decision` itself. It calls
`call_tool()` as normal. If a write tool is suppressed, `result.is_draft == True`
and `result.success == False`. The agent must handle this gracefully — typically
by including the draft result in `AgentResult.response` as a description of what
would have been done.

When `ctx.gate_decision == GateDecision.BLOCKED`, `call_tool()` raises
`ToolBlockedError`. This is caught by `_run_with_timeout()` in the orchestration
layer and surfaces as `state["error"]`.

---

## Configuration — No Breaking Changes

`config/capabilities.yaml` format is unchanged. `config/agents/<name>.yaml` format
is unchanged. The `tools:` field in agent YAML remains, and is now actively
validated at startup against the tool registry (previously documentation only).

The only new requirement: intent keys in `intent_map` must match capability entries.
Existing YAML files already satisfy this.

---

## Module Structure — Updated Convention

```
ze/agents/<name>/
├── __init__.py         # imports tools module to trigger @tool registration
├── agent.py            # _AGENT_INSTRUCTIONS constant + @register class, implements BaseAgent
└── tools.py            # @tool decorated functions
```

Intent→permission mappings are declared in `config/agents/<name>.yaml:intent_map`
(YAML only). There is no `intent_map.py` — the Python module was removed as a
duplicate of the YAML source of truth.

`__init__.py` must import `tools` to trigger `@tool` registration at module import
time. Without this import, declared tools are unknown to the registry.

```python
# ze/agents/research/__init__.py
from . import tools  # registers web_search, summarize, etc.
```

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze.agents.tool` | `@tool`, `ToolSpec`, `ToolAccess`, tool registry |
| `ze.agents.base` | `BaseAgent` with `call_tool()`, lifecycle hooks, config helpers |
| `ze.agents.registry` | `@register`, `register_instance`, `get_agent` |
| `ze.agents.types` | `AgentContext` (now with `gate_decision`), `AgentResult`, `ToolCall` |
| `ze.capability.types` | `GateDecision` — referenced by `call_tool()` and `AgentContext` |
| `ze.errors` | `ToolBlockedError`, `UnknownToolError`, `AgentConfigError` |
| `ze.logging` | Structured per-tool logging in `call_tool()` |
| `ze.settings` | `Settings` — injected via `BaseAgent.__init__` |

New error types to add to `ze/errors.py`:
- `UnknownToolError(ZeError)` — tool name not in registry
- `ToolBlockedError(ZeError)` — tool call rejected by gate
- `AgentConfigError(ZeError)` — startup validation failure

---

## Migrating Existing Agents

### `ResearchAgent`

1. Add `super().__init__(settings)` as first line of `__init__`.
2. Add `tools = ["web_search"]` class attribute.
3. Replace direct `web_search(ctx.prompt, self._tavily)` with
   `await self.call_tool("web_search", ctx, query=ctx.prompt, client=self._tavily)`.
4. Remove `_model()` and `_timeout()` methods — inherited from `BaseAgent`.
5. Replace memory formatting loop with `self._format_memory(ctx)`.
6. Add `from . import tools` to `ze/agents/research/__init__.py`.

### `CompanionAgent`

1. Add `super().__init__(settings)` as first line of `__init__`.
2. Add `tools: list[str] = []` (no tools — explicit is clearer than absent).
3. Remove `_model()` — inherited.
4. Replace memory formatting with `self._format_memory(ctx)`.

### `bootstrap.py`

Replace the hand-written per-agent loop with the generic `_resolve()` pattern.
The `tavily_client`, `openrouter_client`, and `settings` singletons are pre-loaded
into `_dep_map`. No per-agent code remains.

---

## Open Questions

- [ ] **Tool dep injection**: agents currently pass client deps as kwargs to
  `call_tool()`. A future improvement would let the tool declare its dep types
  and have `call_tool()` resolve them from `_dep_map`, so the agent never handles
  external client references. Deferred to Phase 3 when more agents exist and the
  pattern is better understood.
- [ ] **LLM-driven tool selection**: the current model has agents select tools
  imperatively. Phase 4 (workflow agent) may require LLM-driven function calling
  using the `ToolSpec.params` schema. The registry is already structured for this.
- [ ] **Per-tool capability entries**: currently the gate evaluates one
  `(agent, intent)` per request. A future improvement would allow per-tool
  capability overrides (e.g., `email.web_search: autonomous` but
  `email.send_email: confirm`). Deferred — the current model is sufficient for
  Phases 1–3.
