# Ze — Adding a New Agent

This guide explains how to author a new agent. Read it alongside the existing agents
(`ze_personal/agents/research/`, `ze_email/agents/email/`) as working examples.

---

## Before you start

1. Write a spec first via spec-kit: `/speckit-specify` creates `specs/phases/NNN-<name>/spec.md` (see `specs/README.md` for the pipeline). No implementation begins without one.
2. Resolve any open questions in the spec before writing code.
3. Decide which package the agent belongs in (see [docs/package-architecture.md](package-architecture.md)):
   - General assistant agents (research, companion) → `ze_personal/agents/<name>/`
   - Email → `ze_email/agents/<name>/`
   - Prospecting → `ze_prospecting/agents/`
   - Calendar/reminder agents → `ze_calendar/agents/<name>/`
   - Goals/workflow agents → `ze_automation/agents/<name>/`

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
from ze_sdk import tool, ToolAccess
from ze_sdk.types import ToolCall

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
from ze_sdk import agent, BaseAgent
from ze_sdk.types import AgentContext, AgentResult, Intent, Mode
from ze_agents.client import LLMClient
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
    intents = {
        "read":   Intent(Mode.AUTONOMOUS, "Retrieve information."),
        "create": Intent(Mode.CONFIRM,    "Create something."),
    }
    # default_mode = Mode.AUTONOMOUS  # uncomment for read-only agents that accept any intent

    def __init__(self, openrouter_client: LLMClient, settings: Settings) -> None:
        self._client = openrouter_client
        self._settings = settings

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "<name>.working")   # key defined in locales/en.yaml
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
| `self.emit(ctx, key)` | Sends a localized progress message to the client mid-turn (see [Progress messages](#progress-messages)) |

### NLI (entailment / grounding)

Phase 80+ exposes a local cross-encoder via `NLIClient` — already wired in the
bootstrap dep map. Use it when an agent or plugin job needs to compare text pairs
(entailment, contradiction) or score how well a claim is grounded in evidence.

**In agents** — inject `NLIClient` in `__init__`, pass it through `agentic_loop`
deps, and optionally register the shared tools:

```python
from ze_agents.nli import NLIClient
from ze_agents.nli_tools import nli_check_entailment, nli_grounding

@agent
class MyAgent(BaseAgent):
    tools = ["my_tool", "nli_check_entailment", "nli_grounding"]

    def __init__(self, openrouter_client: LLMClient, nli_client: NLIClient) -> None:
        self._client = openrouter_client
        self._nli = nli_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        response, tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            deps={"nli_client": self._nli},
        )
        ...
```

List `ze_agents.nli_tools` in your plugin's `agent_module_paths()` **before** the
agent module so `@tool` registration runs at import time.

**In plugin jobs and services** — type-annotate `nli_client: NLIClient` on the
plugin constructor; the bootstrapper resolves it automatically. For batch scoring
outside the agent loop, call `await nli_client.scores([(premise, hypothesis), ...])`
or `nli_client.grounding_score(hypothesis, evidence_texts)`.

See [sdk.md](sdk.md#nliclient) and [specs/phases/080-nli-client/spec.md](../specs/phases/080-nli-client/spec.md).

### Progress messages

Agents can send localized status strings to the client while they work. The client
displays them as a typing indicator with text instead of a plain spinner.

Call `self.emit(ctx, key)` at any point inside `run()` or inside a tool that has
`reporter` in its deps. Each call resets the 3-second typing indicator timer, so
long-running operations should emit periodically to keep the indicator alive.

**Key convention:** `<domain>.<state>` — e.g. `"news.fetching"`, `"calendar.reading"`.

**Locale files** live inside the plugin's own package at `locales/en.yaml` and
`locales/pt.yaml`. Add entries for every key your agent emits:

```yaml
# plugins/ze-myplugin/ze_myplugin/locales/en.yaml
my_agent:
  working:
    - "⚙️ Working on that..."
    - "⚙️ Let me handle that..."
  searching:
    - "🔍 Searching..."
```

Values can be a single string or a list — list entries are chosen randomly on each
`emit()` call. Template variables use `{name}` Python-format syntax.

The `ZePlugin` base class auto-loads `locales/{locale}.yaml` from within the plugin
package at startup — no override needed as long as the file exists. The app-level
`config/locales/` files are an override layer for deployment-specific customisation.

**Emitting from tools:** pass `reporter` through the agent's deps dict so tools can
emit mid-operation without exposing it to the LLM:

```python
# in _grounded_loop or run():
deps = {"my_store": self._store, "reporter": ctx.reporter}

# in tools.py:
async def my_long_tool(my_store: MyStore, reporter: Any = None) -> dict:
    if reporter is not None:
        await reporter.emit("my_agent.working")
    result = await my_store.do_work()
    return result
```

`reporter` has a non-JSON-primitive type so it is never included in the LLM tool
schema — it is injected silently from deps.

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
plugin's `agent_module_paths()`. Goal and workflow agents are imported directly in
`ze_api/container.py` because `ze-automation` is a core package, not a plugin. The
bootstrapper then resolves each `@agent` class's
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
- [ ] Agent module in the correct domain package — `@agent` class with `name`, `description`, `model`, `intents`, `tools` class attributes
- [ ] Module path added to the package's `ZePlugin.agent_module_paths()` (tools module listed first)
- [ ] All `__init__` parameters are type-annotated
- [ ] All tool calls go through `self.call_tool()` or `self.agentic_loop()`, never direct function calls
- [ ] `tools.py` — all tools decorated with `@tool` (if applicable)
- [ ] Progress keys added to `locales/en.yaml` (and `locales/pt.yaml`) in the plugin package
- [ ] Tests written (including draft + blocked mode)
