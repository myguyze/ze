# Ze — Adding a New Agent

This guide explains how to author a new agent. Read it alongside the existing agents
(`ze_personal/agents/research/`, `ze_email/agents/email/`) as working examples.

---

## Before you start

1. Write a spec in `specs/phases/` first (use `specs/TEMPLATE.md`). No implementation begins without one.
2. Resolve any open questions in the spec before writing code.
3. Decide which package the agent belongs in (see [docs/package-architecture.md](package-architecture.md)):
   - General assistant agents (research, companion) → `ze_personal/agents/<name>/`
   - Email → `ze_email/agents/<name>/`
   - Prospecting → `ze_prospecting/agents/`
   - Calendar/reminder agents → `ze_calendar/agents/<name>/`
   - Goals/workflow agents → `ze_personal/agents/<name>/`

---

## 1. Create the directory and files

```
plugins/<pkg>/<pkg_module>/agents/<name>/
    __init__.py
    agent.py        ← agent class + _AGENT_INSTRUCTIONS
    tools.py        ← tool functions (omit if the agent has no Python tools)
```

---

## 2. Define your tools (`tools.py`)

Tools are async functions decorated with `@tool`. The decorator registers them in the
global tool registry when the module is imported.

```python
from ze_core.orchestration.tool import tool, ToolAccess
from ze_core.orchestration.types import ToolCall

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
`error="suppressed: draft mode"` automatically. `READ` tools are never suppressed.

### Tool parameters

All dependencies (API clients, settings) are passed as keyword arguments from the
agent's `run()` method — tools are pure functions that receive everything they need
via parameters. They do not import from global state or access `self`.

---

## 3. Write the agent (`agent.py`)

```python
from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.capability.types import Mode
from ze_core.openrouter.client import OpenRouterClient
from ze_api.settings import Settings

_AGENT_INSTRUCTIONS = """
You are Ze's <name> agent. <One paragraph: what you do, what you don't do, tone.>

Guidelines:
- <specific constraint>
- <specific constraint>
""".strip()


@agent
class MyAgent(BaseAgent):
    name = "<name>"
    description = """
      One or two sentences describing what this agent handles.
      This text is embedded for cosine-similarity routing — be specific.
    """
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"  # optional — omit if agent already uses Haiku
    vision_capable = False                         # set True if agent should receive image data
    timeout = 30
    tools = ["tool_one", "tool_two"]               # must match @tool-registered names
    intent_map = {
        "read": "Retrieve information.",
        "create": "Create something.",
    }
    capabilities = {
        "read":   Mode.AUTONOMOUS,
        "create": Mode.CONFIRM,
    }

    def __init__(self, openrouter_client: OpenRouterClient, settings: Settings) -> None:
        self._client = openrouter_client
        self._settings = settings

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "<name>.starting")   # optional progress message key
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)

        result = await self.call_tool("tool_one", ctx, param=ctx.prompt, client=self._client)

        response, loop_calls = await self.agentic_loop(ctx, client=self._client)

        return AgentResult(
            agent=self.name,
            output=response,
            tool_calls=loop_calls,
        )
```

### Key `BaseAgent` helpers

| Helper | Description |
|---|---|
| `self._build_system_prompt(instructions, ctx)` | Prepends the identity block (traits, memory, profile) to your agent instructions |
| `self.agentic_loop(ctx, client=…)` | Runs the LLM-driven ReAct tool loop; returns `(response, tool_calls)` |
| `self.call_tool(name, ctx, **kwargs)` | Executes a single tool with draft-mode suppression and structured logging |
| `self._model(ctx)` | Returns the correct model string — primary or `model_simple` based on complexity |
| `self.emit(ctx, key)` | Sends a progress message using a locale translation key |

### Lifecycle hooks

Override these if your agent needs setup/teardown:

```python
async def startup(self) -> None:
    """Called once at app startup, after DI wiring. Use for connection warmup."""

async def shutdown(self) -> None:
    """Called during app shutdown. Use for cleanup."""
```

---

## 4. Register with your plugin

Agents are discovered at startup by importing every module listed in the owning
plugin's `agent_module_paths()`. The bootstrapper then resolves each `@agent` class's
`__init__` parameters by type-matching against the shared `_dep_map` of services.

**To add your agent:** add its module path to the plugin's `agent_module_paths()`.
If your agent has a `tools.py`, list it **before** the agent module so `@tool`
decorators register first.

```python
# In plugins/<pkg>/<pkg_module>/plugin.py
def agent_module_paths(self) -> list[str]:
    return [
        "yourpackage.agents.myagent.tools",   # tools first
        "yourpackage.agents.myagent.agent",
    ]
```

Ze fails hard at startup if an agent declares a tool in `tools = [...]` that isn't
registered — the discrepancy is caught before the app accepts traffic.

**All `__init__` parameters must be type-annotated** — `bootstrap.py` uses
`get_type_hints()` for dependency resolution. Parameters without annotations raise
`AgentConfigError` at startup.

**If your agent needs a dependency not already in `_dep_map`**, add it to the map
in `ze_api/container.py`'s `build_container()` where the dep_map is built, then
pass it to `bootstrap_agents(deps=...)`. The dep_map keys are Python types; values
are the live instances.

---

## 6. Write tests

```
plugins/<pkg>/tests/agents/<name>/
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

## Checklist

- [ ] Spec written and reviewed
- [ ] Agent module in the correct domain package — `@agent` class with `name`, `description`, `model`, `capabilities`, `intent_map`, `tools` class attributes
- [ ] Module path added to the package's `ZePlugin.agent_module_paths()` (tools module listed first)
- [ ] All `__init__` parameters are type-annotated
- [ ] All tool calls go through `self.call_tool()` or `self.agentic_loop()`, never direct function calls
- [ ] `tools.py` — all tools decorated with `@tool` (if applicable)
- [ ] Tests written (including draft + blocked mode)
