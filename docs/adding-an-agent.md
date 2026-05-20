# Ze — Adding a New Agent

This guide explains how to author a new agent from first principles. Read it
alongside the existing agents (`ze/agents/research/`, `ze/agents/companion/`) as
working examples.

---

## Before you start

1. Write a spec in `specs/` first. No implementation begins without one.
2. Resolve any Open Questions in the spec before writing code.

---

## 1. Create the directory and files

```
ze/agents/<name>/
    __init__.py
    agent.py        ← agent class + _AGENT_INSTRUCTIONS
    tools.py        ← tool functions
```

---

## 2. Define your tools (`tools.py`)

Tools are async functions decorated with `@tool`. The decorator registers them in the
global tool registry when the module is imported.

```python
from ze.agents.tool import tool, ToolAccess
from ze.agents.types import ToolCall

@tool(access=ToolAccess.READ, description="Search the web for current information.")
async def web_search(query: str, client: SomeClient, max_results: int = 5) -> ToolCall:
    results = await client.search(query, max_results=max_results)
    return ToolCall(
        tool_name="web_search",
        args={"query": query, "max_results": max_results},
        result=results,
        duration_ms=...,
        success=True,
        error=None,
        is_draft=False,
    )

@tool(access=ToolAccess.WRITE, description="Send an email via Gmail.")
async def send_email(to: str, subject: str, body: str, client: GmailClient) -> ToolCall:
    ...
```

### `ToolAccess` — choose correctly

| Access | Use when |
|---|---|
| `READ` | No external side effects. Safe in any mode including `draft_only`. |
| `WRITE` | Creates, modifies, deletes, or sends anything external. When in doubt, use `WRITE`. |

**Draft mode suppression** — when the capability gate returns `DRAFT`, calling
`self.call_tool("send_email", ctx, ...)` will **not** execute the tool. Instead,
`BaseAgent.call_tool()` returns a `ToolCall` with `is_draft=True` and
`error="suppressed: draft mode"` automatically, without the tool function being
called at all. `READ` tools are never suppressed.

### Tool parameters

All dependencies (API clients, settings) are passed as keyword arguments from the
agent's `run()` method — tools are pure functions that receive everything they need
via parameters. They do not import from global state or access `self`.

---

## 3. Write the agent (`agent.py`)

```python
from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.agents.tool import ToolAccess

_AGENT_INSTRUCTIONS = """
You are Ze's <name> agent. <One paragraph: what you do, what you don't do, tone.>

Guidelines:
- <specific constraint>
- <specific constraint>
""".strip()


@register("<name>")
class MyAgent(BaseAgent):
    name = "<name>"
    tools = ["tool_one", "tool_two"]   # must match @tool-registered names

    def __init__(self, settings, some_client: SomeClient) -> None:
        super().__init__(settings)
        self._client = some_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        system_prompt = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)

        # Run tool calls using self.call_tool() — never call tool functions directly
        result = await self.call_tool("tool_one", ctx, param=ctx.prompt, client=self._client)

        response = await self._complete(
            system_prompt=system_prompt,
            messages=ctx.messages,
            model=self._model(ctx),
        )

        return AgentResult(
            agent=self.name,
            output=response,
            tool_calls=[result],
            memory_proposals=[],   # list[MemoryProposal] if you want to propose facts
        )

    async def stream(self, ctx: AgentContext):
        # Only needed if streaming is used — otherwise raise NotImplementedError
        raise NotImplementedError
```

### Key `BaseAgent` helpers

| Helper | Description |
|---|---|
| `self._build_system_prompt(instructions, ctx)` | Prepends the identity block (traits, memory, profile) to your agent instructions |
| `self._complete(system_prompt, messages, model)` | Calls `OpenRouterClient.complete()` with cost attribution |
| `self._model(ctx)` | Returns the correct model string — primary or `model_simple` based on complexity classification |
| `self._timeout(ctx)` | Returns the configured `timeout_seconds` for this agent |
| `self.call_tool(name, ctx, **kwargs)` | Executes a tool with draft-mode suppression and structured logging |
| `self.call_tool_blocked_check(ctx)` | Raises `ToolBlockedError` immediately if gate is BLOCKED (call at top of `run()` if agent has no tools but still needs to respect the gate) |

### Lifecycle hooks

Override these if your agent needs setup/teardown:

```python
async def startup(self) -> None:
    """Called once at app startup, after DI wiring. Use for connection warmup."""

async def shutdown(self) -> None:
    """Called during app shutdown. Use for cleanup."""
```

---

## 4. Add config (`config/config.yaml`)

Under the `agents:` section:

```yaml
agents:
  <name>:
    enabled: false          # start disabled; flip to true when ready
    description: |
      One or two sentences describing what this agent handles.
      This text is embedded for cosine-similarity routing — be specific.
    model: anthropic/claude-sonnet-4-5
    model_simple: anthropic/claude-haiku-4-5   # optional — omit if agent already uses Haiku
    tools:
      - tool_one
      - tool_two
    timeout_seconds: 30
    intent_map:
      read:   "Retrieve information."
      create: "Create something."
    capabilities:
      read:   autonomous
      create: confirm
```

**Capability modes:**

| Mode | Behaviour |
|---|---|
| `autonomous` | Execute immediately |
| `confirm` | Pause and send inline keyboard (Yes / No / Edit) |
| `draft_only` | Show proposed action, never execute |
| `disabled` | Block entirely |

Default conservatively — use `confirm` for anything that has external side effects
until you're confident in the agent's behaviour.

---

## 5. Wire the instance (`ze/container.py`)

In `build_container()`, construct your agent and register the live instance:

```python
from ze.agents.<name>.agent import MyAgent

my_agent = MyAgent(settings=settings, some_client=some_client)
register_instance(my_agent)
```

The `@register` class decorator registers the *class*. `register_instance()` registers
the live *instance* built with its actual dependencies. Both are needed.

---

## 6. Import the tools module at startup

Tools are registered when the module is imported. Add the import alongside the other
agents in the lifespan (or in `container.py`):

```python
import ze.agents.<name>.tools  # noqa: F401 — triggers tool registration
```

Ze fails hard at startup if an agent declares a tool in `tools: [...]` that isn't
registered — the discrepancy is caught before the app accepts traffic.

---

## 7. Write tests

```
tests/agents/<name>/
    __init__.py
    test_agent.py
    test_tools.py
```

Conventions:

- No real API calls. Mock clients with `AsyncMock`.
- No real DB. Mock `asyncpg` pools with `AsyncMock`.
- Build `AgentContext` directly in tests — it's a dataclass.
- Test draft mode explicitly: pass `gate_decision=GateDecision.DRAFT` in context and
  assert that `WRITE` tools return `is_draft=True` without side effects.
- Test blocked mode: pass `gate_decision=GateDecision.BLOCKED` and assert `ToolBlockedError`.

---

## 8. Enable when ready

Set `enabled: true` in `config/config.yaml`. The routing embedder picks up the new
agent on next startup.

---

## Checklist

- [ ] Spec written and reviewed
- [ ] `config/config.yaml` entry added (`enabled: false`)
- [ ] `ze/agents/<name>/tools.py` — all tools decorated with `@tool`
- [ ] `ze/agents/<name>/agent.py` — class with `@register`, `name`, `tools` class attrs
- [ ] All tool calls go through `self.call_tool()`, never direct function calls
- [ ] Agent wired in `ze/container.py`
- [ ] Tools module imported at startup
- [ ] Tests written (including draft + blocked mode)
- [ ] `enabled: true` when tests pass
