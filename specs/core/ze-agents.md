# ze-agents — Developer API

> **Package:** `core/ze-agents` — `ze_agents/`
> **Status:** Done
> **Supersedes:** [01-agent.md (stale)](01-agent.md)

The entry point for writing agents and tools. Plugin authors import from `ze_sdk.*`
which re-exports everything here.

---

## Purpose

Defines the primitives every agent must implement: `@agent`, `BaseAgent`, `@tool`,
`LLMClient`, `DBPool`, `HarnessHook`, and the agentic loop. This package is the
boundary between the engine (`ze-core`) and domain code (plugins). It has no knowledge
of routing, graph execution, or dependency injection — those live in `ze-core`.

---

## Responsibilities

- `@agent` — registers a class in `AgentRegistry` at import time; raises at duplicate name
- `BaseAgent` — ABC that every agent subclasses; owns `agentic_loop` (ReAct: call LLM → dispatch tool → repeat)
- `@tool` — registers a callable in the tool registry; enforces type annotations
- `LLMClient` — Protocol for `complete` / `stream_complete_with_tools`; injected by engine, never constructed by agents
- `DBPool` — Protocol for `asyncpg.Pool`; injected by engine
- `HarnessHook` — ABC for step-level hooks (tool-call cap, abort signal, delegation)
- `ProgressReporter` — sends `typing` WS frames; locale keys per plugin
- `AppInterface` — ABC for outbound delivery (WebSocket, ntfy); implemented by `ze-api`
- `InputPreprocessor` — voice/image normalisation before the graph runs
- Error hierarchy — all Ze errors subclass `ZeError` from here

---

## Out of Scope

- Graph construction and execution — `ze-core`
- Routing, embedding, capability checking — `ze-core`
- Dependency injection container — `ze-core`
- Plugin registration — `ze-plugin`
- Public re-export surface — `ze-sdk`

---

## Module Location

```
core/ze-agents/ze_agents/
  base_agent.py       ← BaseAgent ABC + agentic_loop
  registry.py         ← @agent decorator + AgentRegistry
  tool.py             ← @tool decorator + ToolAccess
  client.py           ← LLMClient Protocol
  db.py               ← DBPool Protocol
  hooks.py            ← HarnessHook ABC
  errors.py           ← ZeError hierarchy
  settings.py         ← Settings dataclass
  interface/          ← AppInterface ABC, InputPreprocessor, validation
  progress/           ← ProgressReporter, locale translations
  channels/           ← channel tool helpers
  nli.py              ← NLIClient Protocol
  types.py            ← AgentContext, AgentResult, ToolCall, shared types
```

---

## Interface Contract

```python
# registry + decorator
@agent
class MyAgent(BaseAgent):
    name = "my_agent"
    description = "..."
    model = "anthropic/claude-sonnet-4-6"
    intents: list[str] = [...]
    tools: list[str | Callable] = [...]
    timeout: int = 120

    async def run(self, ctx: AgentContext) -> AgentResult: ...

# tool decorator
@tool
async def do_something(arg: str) -> str: ...

# LLM Protocol (injected — never construct directly)
class LLMClient(Protocol):
    async def complete(self, messages, *, model, system, tools) -> str: ...
    async def stream_complete_with_tools(self, ...) -> AsyncIterator[str | ToolCall]: ...
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-logging` | `get_logger` |

No other Ze package dependencies — this is the base layer.

---

## Implementation Notes

`agentic_loop` in `BaseAgent` is the ReAct loop: call the LLM, check for tool calls,
dispatch them, repeat until the LLM produces a final text response or the tool-call
cap hook fires. It calls `HarnessHook.on_tool_call` before each dispatch so the engine
can abort, log, or transform.
