# Ze SDK Reference

`ze-sdk` is the single dependency plugin authors declare. It re-exports every public
symbol from `ze-agents`, `ze-proactive`, `ze-memory`, and `ze-onboarding` through a flat,
stable surface.
Plugin packages never import `ze-core` directly.

---

## Import map

```python
from ze_sdk import ZePlugin, agent, tool, ToolAccess, BaseAgent, get_logger, Settings, DBPool
from ze_sdk.types import AgentContext, AgentResult, ToolCall, GateDecision, Mode, AbortToken, Action, Notification
from ze_sdk.proactive import ProactiveJob, proactive_job, ProactiveScheduler, ProactiveNotifier, PushLogStore, PushLogEntry
from ze_sdk.channels import Channel, ChannelType, ChannelHandle, Message, SentMessage, Thread, ThreadMessage, ChannelSendError
from ze_sdk.memory import MemoryContext, Fact, Episode, Procedure, Entity, TaskState, RetrievalRequest, MemoryStore, PostgresMemoryStore
from ze_sdk.onboarding import OnboardingProvider, OnboardingStep, OnboardingField, OnboardingSeed, OnboardingResult
from ze_sdk.errors import ZeError, AgentError, ToolBlockedError, AgentAbortedError, AgentConfigError, ChannelSendError
```

---

## `ze_sdk` — core authoring API

| Symbol | What it is |
|--------|-----------|
| `ZePlugin` | Abstract base class for domain extensions. Override only the hooks you need. |
| `agent` | Class decorator that registers a `BaseAgent` subclass in the global `AgentRegistry`. |
| `tool` | Function decorator that registers an async function as a callable tool. |
| `ToolAccess` | Enum — `READ` or `WRITE`. Controls draft-mode suppression. |
| `BaseAgent` | Abstract base class all agents inherit. Provides `agentic_loop`, `call_tool`, `emit`, and `_build_system_prompt`. |
| `get_logger` | Structured logger factory. Always call as `get_logger(__name__)`. |
| `Settings` | Settings dataclass bridge. Agents receive this via DI — never construct it yourself. |
| `DBPool` | Structural `Protocol` for asyncpg connection pools. Use as a type hint in `__init__`. |

---

## `ze_sdk.types` — runtime types

### `AgentContext`

Passed to every `BaseAgent.run()` call. Contains everything the agent needs for one turn.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Unique conversation/graph thread ID. |
| `prompt` | `str` | The user's message for this turn. |
| `intent` | `str` | Intent key chosen by the router (e.g. `"read"`, `"create"`). |
| `gate_decision` | `GateDecision` | Capability gate outcome — controls tool execution. |
| `memory` | `MemoryContext \| None` | Retrieved memory for this turn. |
| `contacts` | `ContactsContext \| None` | Retrieved contacts for this turn. |
| `tool_calls` | `list[ToolCall]` | Tool calls accumulated so far in this turn. |
| `messages` | `list[dict]` | Conversation history (OpenAI message format). |
| `persona` | `dict` | Active persona dials. |
| `model` | `str \| None` | Override model string. Falls back to agent's class attribute. |
| `reporter` | `ProgressReporter \| None` | Emit progress messages via `self.emit(ctx, key)`. |
| `extensions` | `dict[str, ...]` | Arbitrary msgpack-serializable data (e.g. `goal_id`). |

Fields `identity_builder`, `abort_token`, and `memory_store` are runtime-only — never checkpoint a context where they are set.

### `AgentResult`

Returned from `BaseAgent.run()`.

| Field | Type | Description |
|-------|------|-------------|
| `agent` | `str` | Agent name (matches `BaseAgent.name`). |
| `response` | `str` | Final text response to show the user. |
| `tool_calls` | `list[ToolCall]` | All tool calls made during this turn. |
| `tokens_used` | `int` | Token count for telemetry. |
| `memory_proposals` | `list` | Proposed facts for memory extraction. |
| `contact_proposals` | `list` | Proposed contacts for consolidation. |
| `extensions` | `dict[str, Any]` | Arbitrary data forwarded to graph state. |

### `ToolCall`

Structured record of a single tool invocation.

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Registered tool name. |
| `args` | `dict` | Arguments passed to the tool. |
| `result` | `Any` | Return value, or `None` on failure. |
| `duration_ms` | `int` | Wall-clock execution time. |
| `success` | `bool` | Whether the tool ran without exception. |
| `error` | `str \| None` | Error message if `success=False`. |
| `is_draft` | `bool` | `True` when a WRITE tool was suppressed by the gate. |

### `GateDecision`

Controls which tools the capability gate allows.

| Value | Meaning |
|-------|---------|
| `EXECUTE` | All tools run normally. |
| `DRAFT` | WRITE tools are suppressed (`is_draft=True`); READ tools run. |
| `AWAIT_CONFIRMATION` | Agent must pause and request user confirmation. |
| `BLOCKED` | All tools raise `ToolBlockedError`. |

### `Mode`

Configured per-intent on an agent class. Maps the intent to a gate policy.

| Value | Behaviour |
|-------|-----------|
| `AUTONOMOUS` | Always `EXECUTE`. |
| `CONFIRM` | Always `AWAIT_CONFIRMATION`. |
| `DRAFT_ONLY` | Always `DRAFT`. |
| `DISABLED` | Always `BLOCKED`. |

### `AbortToken`

Async signal that cancels a running `agentic_loop` between iterations.

```python
token = AbortToken()
token.abort(reason="user cancelled")   # signals the loop to stop
token.is_set                            # True after abort()
```

### `Action` and `Notification`

Returned from `AppInterface` to the transport layer. Plugin authors rarely construct these directly — they come from `BaseAgent.run()` returning an `AgentResult`, which the graph nodes convert to frames.

---

## `BaseAgent` — abstract base class

All agents subclass `BaseAgent` and decorate the class with `@agent`.

### Class attributes

```python
@agent
class MyAgent(BaseAgent):
    name         = "my_agent"           # unique, snake_case — used for routing
    description  = "What this agent does."  # embedded for cosine-similarity routing
    model        = "anthropic/claude-sonnet-4-5"
    model_simple = None                 # optional lighter model for simple turns
    vision_capable = False              # set True to receive image data in ctx
    timeout      = 30                   # seconds
    tools        = ["tool_a", "tool_b"] # @tool-registered names
    intent_map   = {"read": "Retrieve info.", "write": "Create something."}
    capabilities = {"read": Mode.AUTONOMOUS, "write": Mode.CONFIRM}
```

All attributes except `name` have defaults — only override what differs.

### Abstract method

```python
@abstractmethod
async def run(self, ctx: AgentContext) -> AgentResult: ...
```

### Instance helpers

#### `self._build_system_prompt(instructions, ctx, **extra) -> str`

Prepends the persona/memory identity block to your agent instructions. Always call this instead of concatenating manually.

```python
system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
```

Pass `**extra` to use `.format()` placeholders in `_AGENT_INSTRUCTIONS`.

#### `await self.agentic_loop(ctx, client, messages, system, deps=None, tool_names=None, max_iterations=6, max_tokens=2000) -> tuple[str, list[ToolCall]]`

Drives an LLM ReAct loop: the model picks tools, ze dispatches them through `call_tool`, results are appended to `messages`, and the loop repeats until the model produces a text response.

- `client` — the `LLMClient` injected via `__init__`.
- `messages` — conversation history. Pass `ctx.messages` for full history.
- `system` — built by `_build_system_prompt`.
- `deps` — internal dependencies the LLM cannot provide (e.g. `{"client": self._client}`). Ze merges them into tool kwargs automatically.
- `tool_names` — defaults to `self.tools`.
- Returns `(final_response_text, list_of_all_tool_calls)`.

#### `await self.call_tool(name, ctx, **kwargs) -> ToolCall`

Executes a single registered tool with capability enforcement and hook dispatch.

- WRITE tools return `is_draft=True` when `gate_decision == DRAFT`.
- Any tool raises `ToolBlockedError` when `gate_decision == BLOCKED`.
- Pass all tool dependencies (clients, settings) as keyword arguments.

#### `await self.emit(ctx, key, **kwargs)`

Sends a progress message to the client using a locale translation key. No-op when no reporter is attached (e.g. in tests).

#### `self._model(ctx) -> str`

Returns the active model string — respects `ctx.model` overrides and falls back to `self.model`.

### Lifecycle hooks

```python
async def startup(self) -> None:
    """Called once after DI wiring. Use for connection warmup."""

async def shutdown(self) -> None:
    """Called during app shutdown. Use for cleanup."""
```

---

## `@agent` decorator

```python
from ze_sdk import agent

@agent
class MyAgent(BaseAgent): ...
```

Registers the class in the global `AgentRegistry` when the module is imported. The `bootstrap.py` entry point imports all modules listed in `ZePlugin.agent_module_paths()` to trigger registration. There is nothing else to call — the decorator is the entire registration.

---

## `@tool` decorator and `ToolAccess`

```python
from ze_sdk import tool, ToolAccess

@tool(access=ToolAccess.READ, description="Fetch data from the database.")
async def get_record(id: str, db: DBPool) -> str:
    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM records WHERE id = $1", id)
        return str(row)
```

### Rules

- Tools must be `async def`.
- All parameters the LLM cannot infer must be typed — they are injected via `deps` in `agentic_loop` or passed explicitly via `call_tool(**kwargs)`.
- `ToolAccess.READ` — no external side effects. Runs in any gate state.
- `ToolAccess.WRITE` — creates, modifies, deletes, or sends. Suppressed in DRAFT mode.

### Tool parameters

| Parameters | Provided by |
|------------|-------------|
| Simple scalar types (`str`, `int`, `bool`) | LLM |
| Clients, stores, settings | `deps` dict in `agentic_loop` or explicit kwargs in `call_tool` |

### OpenRouter web search

Declare `"openrouter:web_search"` in `tools` to let the model trigger a web search. No Python tool function is needed — OpenRouter executes it and the result appears in the conversation automatically.

```python
tools = ["openrouter:web_search", "my_tool"]
```

---

## `ZePlugin` — extension point

```python
from ze_sdk import ZePlugin

class MyPlugin(ZePlugin):
    ...
```

Override only the hooks your plugin needs. All methods have no-op defaults.

### Container-level hooks

| Method | Signature | Purpose |
|--------|-----------|---------|
| `agents()` | `-> list[type[BaseAgent]]` | Agents to register (rarely used — prefer `agent_module_paths`). |
| `jobs()` | `-> list[Any]` | Proactive job instances to register. |
| `onboarding()` | `-> OnboardingProvider \| None` | Onboarding provider for first-run setup. |
| `migrations_path()` | `-> Path \| None` | `classmethod`. Path to the Alembic `versions/` directory. |
| `agent_module_paths()` | `-> list[str]` | Module paths imported at bootstrap to trigger `@agent`/`@tool` registration. List tools module before agent module. |

### Graph-level hooks

| Method | Signature | Purpose |
|--------|-----------|---------|
| `state_extensions()` | `-> type \| None` | A `TypedDict` subclass whose fields are merged into `AgentState`. |
| `checkpoint_serde_modules()` | `-> tuple[str, ...]` | `types.py` module paths scanned for checkpoint-serializable dataclasses/enums. |
| `pre_route_node()` | `-> Callable \| None` | An async graph node inserted between preprocess and embed_route. |
| `graph_nodes()` | `-> dict[str, Callable]` | Additional LangGraph nodes keyed by node name. |
| `graph_edges(builder)` | `-> None` | Wire plugin nodes into the graph at build time. |
| `configurable_services()` | `-> dict[str, Any]` | Services injected into `config["configurable"]` every turn. |

### Lifecycle hooks

| Method | Signature | Purpose |
|--------|-----------|---------|
| `startup(container)` | `async -> None` | Called once after the container is fully built. Use for DB connections, credential refresh, scheduler start. |
| `shutdown()` | `async -> None` | Called during app shutdown in reverse startup order. |

### Proactive job registration

```python
def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True) -> None:
    scheduler.add_cron_job(my_job, cron="0 8 * * *")
```

Called by `ZeContainer` after startup. Use it to add cron jobs to the `ProactiveScheduler`.

---

## `ze_sdk.onboarding` — setup providers

| Symbol | Description |
|--------|-------------|
| `OnboardingProvider` | Protocol returned by `ZePlugin.onboarding()`. Defines `steps()` and `handle_submission()`. |
| `OnboardingStep` | One setup step, owned by a plugin and rendered by the runtime. |
| `OnboardingField` | A field inside a form step: text, textarea, select, multiselect, boolean, chips, etc. |
| `OnboardingChoice` | A choice/card option for non-form steps. |
| `OnboardingSubmission` | Structured values submitted by the app for a step. |
| `OnboardingSeed` | A typed proposed write: profile facet, memory fact, plugin setting, contact, etc. |
| `OnboardingResult` | Provider response containing seeds and optional follow-up steps. |

Providers should only describe setup needs and return seeds. They must not import
`ze_api`, write directly to global memory, or own the global flow. The runtime reviews
durable seeds before applying them through deployment adapters. See
[onboarding.md](onboarding.md) for the end-to-end flow.

---

## `ze_sdk.proactive` — job scheduling

| Symbol | Description |
|--------|-------------|
| `ProactiveJob` | Protocol. Implement `run(settings, notifier) -> None` and set `job_id: str`, `schedule: str`. |
| `proactive_job` | Class decorator that marks a class as a proactive job and registers it. |
| `ProactiveScheduler` | APScheduler wrapper. Call `add_cron_job(job, cron=...)` inside `register_proactive_jobs`. |
| `ProactiveNotifier` | Push delivery. Sends messages via WebSocket or ntfy. |
| `PushLogStore` | Delivery audit log. Persists which notifications have been sent. |
| `PushLogEntry` | Dataclass for a single log entry. |

---

## `ze_sdk.channels` — channel abstraction

| Symbol | Description |
|--------|-------------|
| `Channel` | ABC for message channels (email, SMS, etc.). Override `send`, `receive`, `list_threads`. |
| `ChannelType` | Enum — `EMAIL`, etc. |
| `ChannelHandle` | A resolved contact handle for a channel (address + type). |
| `Message` | Inbound or draft message. |
| `SentMessage` | Confirmation of a sent message with provider message ID. |
| `Thread` | Conversation thread in a channel. |
| `ThreadMessage` | Single message within a thread. |
| `ChannelSendError` | Raised when a channel `send()` fails. |

---

## `ze_sdk.memory` — memory types

Plugin agents rarely read memory directly — `ctx.memory` is pre-populated. Use these types for type hints and for direct store access in proactive jobs.

| Symbol | Description |
|--------|-------------|
| `MemoryContext` | Retrieval result: `facts`, `episodes`, `procedures`, `entities`, `task_state`, `profile`. |
| `Fact` | A subject-predicate-value triple stored persistently. |
| `Episode` | A summarised conversation episode. |
| `Procedure` | A user-taught step-by-step procedure. |
| `Entity` | A named entity extracted from conversations. |
| `TaskState` | Current execution state for a running task/goal. |
| `RetrievalRequest` | Parameters for a `MemoryStore.retrieve()` call. |
| `MemoryStore` | Protocol for memory stores. |
| `PostgresMemoryStore` | Default implementation backed by asyncpg + pgvector. |

---

## `ze_sdk.errors` — error hierarchy

Always raise a typed `ZeError` subclass. Never raise bare `Exception` or `ValueError`.

| Error class | When to raise |
|-------------|--------------|
| `ZeError` | Base class. Do not raise directly. |
| `AgentError` | Unrecoverable agent-level failure (unexpected LLM response, missing result). |
| `AgentAbortedError` | Agent loop was cancelled via `AbortToken`. |
| `AgentConfigError` | Misconfiguration detected at startup (missing type hints, unregistered tool). |
| `ToolBlockedError` | Tool call was rejected because the gate decision is `BLOCKED`. |
| `ChannelSendError` | Channel `send()` failed. |

Import from `ze_sdk.errors`:

```python
from ze_sdk.errors import AgentError, ToolBlockedError
```

---

## `DBPool` protocol

```python
from ze_sdk import DBPool

class MyStore:
    def __init__(self, pool: DBPool) -> None:
        self._pool = pool

    async def get(self, id: str) -> dict:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM my_table WHERE id = $1", id)
```

`DBPool` is a structural Protocol satisfied by any asyncpg `Pool`. Use it as a type hint — the DI container resolves it by type at startup.
