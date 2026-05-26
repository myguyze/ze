# Ze Core — Container & Discovery — Spec

## Purpose

Wire all Ze Core components into a single shared container for the lifetime of
the application. The container is responsible for:

1. Discovering and importing agent modules.
2. Validating agent class attributes.
3. Instantiating enabled agents via type-based dependency injection.
4. Constructing all framework singletons (router, gate, memory store, graph).
5. Providing a clean `close()` lifecycle hook.

Ze Core's container is intentionally minimal — it wires the framework, not the
application. Ze-specific concerns (Telegram bot, proactive schedulers, cost
telemetry, browser sidecar) are not part of Ze Core's container.

---

## Responsibilities

- Scan `agents/` for subdirectories containing `agent.py`; import them to fire
  `@agent` decorators as a side effect.
- Validate all registered agent classes after discovery.
- Instantiate enabled agents by resolving `__init__` parameter types against a
  caller-supplied dependency map.
- Construct `EmbeddingRouter`, `CapabilityGate`, `MemoryStore`, and the LangGraph
  graph.
- Register live agent instances so `get_agent()` works at graph execution time.
- Call `agent.startup()` on every instantiated agent.
- Call `agent.shutdown()` on every instantiated agent during `close()`.

## Out of Scope

- Does not manage Telegram, Slack, or any other transport.
- Does not schedule proactive jobs.
- Does not manage the Alembic migration lifecycle.
- Does not provide a REST API or health endpoint.
- Does not create DB schemas — assumes migrations have been applied.

---

## Directory Convention

Ze Core discovers agents by scanning the `agents/` directory relative to the
**application root** — the directory containing `config.yaml`, passed to
`Container.from_config()`.

```
myapp/
  config.yaml          ← application root
  agents/
    research/
      __init__.py
      agent.py         ← imported → @agent fires → ResearchAgent registered
      tools.py
    calendar/
      __init__.py
      agent.py         ← imported → @agent fires → CalendarAgent registered
      tools.py
```

Only subdirectories that contain an `agent.py` file are imported. Other files and
subdirectories inside `agents/` are ignored.

Subdirectories are imported in sorted order — deterministic across restarts.

---

## Container Dataclass

`ze_core/container.py`

```python
@dataclass
class Container:
    settings: Settings
    pool: asyncpg.Pool
    checkpointer_pool: asyncpg.Pool
    embedder: SentenceTransformer
    openrouter_client: OpenRouterClient
    router: EmbeddingRouter
    capability_gate: CapabilityGate
    memory_store: MemoryStore
    memory_consolidator: MemoryConsolidator
    graph: CompiledGraph

    async def close(self) -> None:
        """Shut down all agents, then release shared resources."""
        from ze_core.orchestration.registry import get_enabled_instances
        for instance in get_enabled_instances().values():
            try:
                await instance.shutdown()
            except Exception as exc:
                log.warning("agent_shutdown_failed", agent=instance.name, error=str(exc))
        await self.openrouter_client.aclose()
        await dispose_checkpointer_pool(self.checkpointer_pool)
        await self.pool.close()
        log.info("container_closed")
```

---

## `Container.from_config()`

```python
@classmethod
async def from_config(
    cls,
    config_path: Path,
    deps: dict[type, Any] | None = None,
) -> "Container":
```

`config_path` is the path to `config.yaml`. The application root is inferred as
`config_path.parent`.

`deps` is the caller-supplied dependency map (type → instance). Ze Core resolves
agent `__init__` parameters against this map. Required types that are always
present in the map:

| Type | Always required |
|---|---|
| `OpenRouterClient` | Yes |
| `Settings` | Yes |

All other types are optional — if an agent's `__init__` requires a type not in
`deps`, construction fails with `AgentConfigError`.

### Build sequence

```
1.  Load Settings from config_path.
2.  Create asyncpg pool (main + checkpointer).
3.  Load SentenceTransformer embedder.
4.  Build OpenRouterClient.
5.  Discover and import agent modules (_discover_agents).
6.  Validate all registered agent classes (_validate_registry).
7.  Instantiate enabled agents (_instantiate_agents).
8.  Call agent.startup() on each instantiated agent (concurrently).
9.  Build EmbeddingRouter (reads from registry — embeddings computed here).
10. Build CapabilityGate (stateless — no args).
11. Build MemoryStore.
12. Build MemoryConsolidator.
13. Build LangGraph checkpointer (AsyncPostgresSaver) and compile graph.
14. Return Container.
```

Steps 1–4 are sequential (each depends on the previous). Steps 8 are concurrent
(`asyncio.gather`). Steps 9–13 are sequential (router requires the registry to be
populated first).

---

## Agent Discovery

`ze_core/container.py` (private)

```python
def _discover_agents(app_root: Path, package: str) -> None:
    agents_dir = app_root / "agents"
    if not agents_dir.exists():
        raise AgentConfigError(f"agents/ directory not found at {agents_dir}")

    for subdir in sorted(agents_dir.iterdir()):
        if subdir.is_dir() and (subdir / "agent.py").exists():
            module_path = f"{package}.agents.{subdir.name}.agent"
            importlib.import_module(module_path)
```

`package` is the application package name — the Python package that contains the
`agents/` directory. Ze Core infers this from `config_path` and the Python path:
it is the top-level package that owns `config.yaml`'s parent directory.

`@agent` fires as a side effect of each import — no explicit registration call.
Duplicate agent names raise `AgentConfigError` at import time (enforced by `@agent`).

---

## Startup Validation

`ze_core/container.py` (private), called after discovery:

```python
def _validate_registry(settings: Settings) -> None:
    from ze_core.orchestration.registry import get_registered_agents
    from ze_core.orchestration.tool import registered_tools

    tool_reg = registered_tools()
    registered = get_registered_agents()

    for name, cls in registered.items():
        if not getattr(cls, "name", ""):
            raise AgentConfigError(f"{cls.__name__} must define a non-empty `name`")
        if not getattr(cls, "description", "").strip():
            raise AgentConfigError(f"Agent {name!r} must define a non-empty `description`")

        for tool_name in getattr(cls, "tools", []):
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {name!r} declares unknown tool {tool_name!r}"
                )

        capabilities = getattr(cls, "capabilities", {})
        for intent in getattr(cls, "intent_map", {}):
            if intent not in capabilities:
                raise AgentConfigError(
                    f"Agent {name!r} intent_map key {intent!r} not in capabilities"
                )

    enabled = {n: c for n, c in registered.items() if getattr(c, "enabled", True)}
    if not enabled:
        raise RoutingError("No enabled agents found after discovery")
```

Validation aborts startup on the first error. A misconfigured agent must not reach
a running server.

---

## Dependency Injection

`ze_core/container.py` (private):

```python
def _instantiate_agents(
    registered: dict[str, type[BaseAgent]],
    deps: dict[type, Any],
) -> dict[str, BaseAgent]:
    from ze_core.orchestration.registry import register_instance

    instances: dict[str, BaseAgent] = {}
    for name, cls in registered.items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls, deps)
        register_instance(name, instance)
        instances[name] = instance
    return instances
```

### `_resolve()`

Instantiates `cls` by matching `__init__` parameter type annotations against
`deps`:

```python
def _resolve(cls: type[BaseAgent], deps: dict[type, Any]) -> BaseAgent:
    hints = get_type_hints(cls.__init__)
    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        annotation = hints.get(param_name)
        if annotation is None:
            raise AgentConfigError(
                f"{cls.__name__}.__init__ parameter {param_name!r} has no type annotation"
            )
        if annotation not in deps:
            raise AgentConfigError(
                f"No dependency registered for {annotation!r} "
                f"(required by {cls.__name__}). Add it to deps before calling from_config()."
            )
        kwargs[param_name] = deps[annotation]

    return cls(**kwargs)
```

Every `__init__` parameter must be type-annotated and present in `deps`. There are
no positional-only or variadic parameters in agent constructors. `self` is skipped.

### Dependency map construction

Ze Core builds the base dependency map internally (containing `OpenRouterClient`
and `Settings`). The caller's `deps` dict is merged on top. Caller-supplied values
take precedence.

```python
internal_deps = {
    OpenRouterClient: openrouter_client,
    Settings: settings,
    asyncpg.Pool: pool,
}
merged = {**internal_deps, **(deps or {})}
```

Applications that need to inject additional types (e.g. `GoogleCredentials`,
`WorkflowStore`) include them in `deps`.

---

## Agent Instance Registry

`ze_core/orchestration/registry.py`

Two separate registries:

| Registry | Keys | Populated by | Read by |
|---|---|---|---|
| Class registry (`_registry`) | `name → type[BaseAgent]` | `@agent` at import time | router, gate, validation |
| Instance registry (`_instances`) | `name → BaseAgent` | `register_instance()` at startup | `get_agent()` in `execute_tool` |

```python
_registry:  dict[str, type[BaseAgent]] = {}
_instances: dict[str, BaseAgent] = {}


def agent(cls: type) -> type:
    name = getattr(cls, "name", None)
    if not name:
        raise AgentConfigError(f"{cls.__name__} must define a `name` class attribute")
    if name in _registry:
        raise AgentConfigError(f"Duplicate agent name {name!r}")
    _registry[name] = cls
    return cls


def register_instance(name: str, instance: BaseAgent) -> None:
    _instances[name] = instance


def get_agent(name: str) -> BaseAgent:
    if name not in _instances:
        raise UnknownAgentError(f"No registered instance for agent: {name!r}")
    return _instances[name]


def get_agent_class(name: str) -> type[BaseAgent]:
    if name not in _registry:
        raise UnknownAgentError(f"No registered class for agent: {name!r}")
    return _registry[name]


def get_registered_agents() -> dict[str, type[BaseAgent]]:
    return dict(_registry)


def get_enabled_agents() -> dict[str, type[BaseAgent]]:
    return {n: c for n, c in _registry.items() if getattr(c, "enabled", True)}


def get_enabled_instances() -> dict[str, BaseAgent]:
    return dict(_instances)
```

The class registry is populated at import time and never cleared. The instance
registry is populated at startup. Both are module-level globals — this is the
only intentional use of mutable module-level state in Ze Core.

---

## Tool Registry

`ze_core/orchestration/tool.py`

The `@tool` decorator registers async functions as typed, access-controlled tools:

```python
@tool(access=ToolAccess.READ, description="Search the web for current information.")
async def web_search(query: str, client: OpenRouterClient) -> str:
    ...
```

Tools are registered at import time (side effect of importing `tools.py`).
`_discover_agents()` does not import `tools.py` files directly — each `agent.py`
must import its own `tools.py` (or the container must import a shared tools module
before validation runs).

```python
class ToolAccess(str, Enum):
    READ  = "read"   # executes in any gate state including DRAFT
    WRITE = "write"  # suppressed (returns draft ToolCall) when gate is DRAFT


def tool(*, access: ToolAccess | str, description: str) -> Callable:
    """Register an async function as a Ze Core tool."""


def get_tool(name: str) -> ToolSpec:
    """Return ToolSpec for name. Raises UnknownToolError if missing."""


def registered_tools() -> dict[str, ToolSpec]:
    """Return all registered tools."""
```

Tool schemas (`ToolSpec.llm_schema()`) are generated in OpenAI function-calling
format. Parameters with non-JSON-primitive type annotations (e.g. `OpenRouterClient`,
`asyncpg.Pool`) are excluded from the schema — the LLM never sees internal deps.

---

## LangGraph Serialiser

Ze Core registers its domain types with `JsonPlusSerializer` so LangGraph can
checkpoint `AgentState` correctly:

```python
serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("ze_core.routing.types",     "SubTask"),
        ("ze_core.routing.types",     "RoutingEnvelope"),
        ("ze_core.agents.types",      "ToolCall"),
        ("ze_core.agents.types",      "AgentResult"),
        ("ze_core.agents.types",      "AgentContext"),
        ("ze_core.capability.types",  "GateDecision"),
        ("ze_core.memory.types",      "MemoryContext"),
        ("ze_core.memory.types",      "UserFact"),
        ("ze_core.memory.types",      "Episode"),
        ("ze_core.memory.types",      "UserProfile"),
    ]
)
checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
await checkpointer.setup()
```

The module paths must match exactly. If a Ze Core type is added to `AgentState`,
its module path must be added here.

---

## Settings

`ze_core/settings.py`

Ze Core's `Settings` class uses Pydantic `BaseSettings`. Secrets come from
environment variables (or `.env`). Structural config comes from `config.yaml`.

Required environment variables:

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM gateway |
| `DATABASE_URL` | asyncpg pool (async runtime) |
| `DATABASE_URL_SYNC` | psycopg2 (Alembic CLI only) |

Optional environment variables with defaults:

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_BASE_URL` | `"https://openrouter.ai/api/v1"` | API endpoint |
| `SESSION_INACTIVITY_MINUTES` | `30` | History reset threshold |
| `CONSOLIDATION_ENABLED` | `true` | Enable nightly memory consolidation |
| `LOG_LEVEL` | `"INFO"` | structlog level |

`Settings.config` returns the parsed YAML dict from `config.yaml`. All structural
config (routing thresholds, model assignments, memory settings) lives in YAML, not
in environment variables.

---

## Full Build Sequence Example

```python
from pathlib import Path
from ze_core.container import Container
from ze_core.openrouter.client import OpenRouterClient

# Application wires its own deps
custom_deps = {
    GoogleCredentials: GoogleCredentials.from_env(),
    WorkflowStore: WorkflowStore(pool=pool),
}

container = await Container.from_config(
    config_path=Path("config/config.yaml"),
    deps=custom_deps,
)

# Application uses container
graph_result = await container.graph.ainvoke(state, config)

# On shutdown
await container.close()
```

---

## Startup Error Taxonomy

| Error | Raised by | Condition |
|---|---|---|
| `AgentConfigError` | `@agent` | Duplicate agent name |
| `AgentConfigError` | `@agent` | Missing `name` attribute |
| `AgentConfigError` | `_validate_registry` | Empty `name` or `description` |
| `AgentConfigError` | `_validate_registry` | Tool name not in tool registry |
| `AgentConfigError` | `_validate_registry` | `intent_map` key not in `capabilities` |
| `AgentConfigError` | `_resolve` | `__init__` param has no type annotation |
| `AgentConfigError` | `_resolve` | Required type not in `deps` |
| `AgentConfigError` | `_discover_agents` | `agents/` directory not found |
| `RoutingError` | `_validate_registry` | No enabled agents after discovery |
| `InterfaceConfigError` | startup validation | `confirmation_style` missing or wrong method |

All errors abort startup. Ze Core does not attempt partial recovery — a
misconfigured application must not start.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `asyncpg` | DB pool creation |
| `sentence_transformers` | Embedder singleton |
| `langgraph` | Graph compilation, `AsyncPostgresSaver` |
| `ze_core.orchestration.registry` | Class and instance registries |
| `ze_core.orchestration.tool` | Tool registry |
| `ze_core.routing.router` | `EmbeddingRouter` construction |
| `ze_core.capability.gate` | `CapabilityGate` construction |
| `ze_core.memory.store` | `MemoryStore` construction |
| `ze_core.memory.consolidator` | `MemoryConsolidator` construction |
| `ze_core.orchestration.graph` | `build_graph()` |
| `ze_core.errors` | `AgentConfigError`, `RoutingError`, `InterfaceConfigError` |
| `ze_core.logging` | Structured logging |
