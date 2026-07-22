# Ze Core Split — ze-agents + ze-proactive

> **Packages:** `core/ze-agents/` (new), `core/ze-proactive/` (new), `core/ze-core/` (slimmed)
> **Phase:** 48
> **Status:** Done
> **Prerequisite:** Phase 49 (ze-sdk) depends on this split; implement this phase first.

---

## Problem

Ze-core is a monolith. A package claimed to be "pure infrastructure — no domain knowledge" contains:

- The developer API for building agents (`BaseAgent`, `@agent`, `@tool`)
- The plugin contract (`ZePlugin`)
- A job scheduling framework (`ProactiveScheduler`, `ProactiveJob`, `ProactiveNotifier`)
- A channel abstraction (`Channel`, `ChannelRegistry`, `ChannelType`)
- Application interface contracts (`AppInterface`, `InputPreprocessor`)
- A progress reporting system
- The LangGraph orchestration engine
- An OpenRouter HTTP client
- Embedding routing infrastructure
- A capability gate
- Cost telemetry
- A DI container

None of these have a reason to live in the same package. The result:

- Every plugin depends on ze-core, pulling in the entire engine as a transitive dependency for agent authoring.
- Internal paths (`ze_core.orchestration.base_agent`, `ze_core.proactive.notifier`) become de facto public API, making refactoring expensive.
- Ze-core cannot evolve its engine internals without risking plugin breakage.
- There is no signal distinguishing "this is stable developer API" from "this is engine internals."

---

## Proposed Split

Three packages emerge from ze-core. Ze-core itself becomes a pure execution engine.

### `ze-agents` — The Developer API

What plugin and agent authors work with. Defines the contracts that ze-core's engine implements against. Ze-core depends on ze-agents, not the other way around.

**Responsibilities:**
- Agent authoring: `BaseAgent`, `@agent` decorator, agent registry
- Tool authoring: `@tool`, `ToolAccess`, `ToolSpec`
- Plugin contract: `ZePlugin` ABC with lifecycle hooks
- Shared execution types: `AgentContext`, `AgentResult`, `ToolCall`, `GateDecision`, `Mode`
- Application interface: `AppInterface` ABC, `InputPreprocessor`, `RawInput`, `InvokeResult`
- Channel contract: `Channel` ABC, `ChannelType`, `ChannelHandle`, `Message`, `SentMessage`, `Thread`, `ThreadMessage`
- Progress: `ProgressReporter` (so `self.emit()` in agents works without importing ze-core)
- Delegate mechanism: `delegate_to_agent` tool
- Hooks: `HookPoint`, `register_hook`, `BaseHook` (agent-level hooks, not graph internals)
- Errors: full `ZeError` hierarchy (errors are contracts too)
- Logging: `get_logger` (utility shared by all ze packages)
- Settings: base `Settings` class (ze-core-level config — api_key, database_url, log_level)

**Does NOT include:**
- Graph building, nodes, or LangGraph wiring
- Routing (EmbeddingRouter, ComplexityEstimator)
- Capability gate implementation (only the types: GateDecision, Mode)
- The OpenRouter client implementation (only a protocol/type reference)
- Telemetry internals
- The DI container

### `ze-proactive` — The Job Framework

Standalone scheduling and notification infrastructure. Currently `ze_core/proactive/` with zero coupling to the engine.

**Responsibilities:**
- Job protocol: `ProactiveJob` ABC, `@proactive_job` decorator
- Scheduler: `ProactiveScheduler` (APScheduler wrapper with cron + one-shot support)
- Notifier: `ProactiveNotifier` (push abstraction backed by `AppInterface`)
- Persistence: `PushLogStore`, `PushLogEntry` (sent-notification log, deduplication)

**Depends on:** ze-agents (for `AppInterface` — `ProactiveNotifier` sends via it)

**Does NOT include:** anything from ze-core's engine.

### `ze-core` (slimmed — the Engine)

Pure LangGraph execution engine. No developer-facing authoring API.

**Responsibilities:**
- Graph construction: `build_graph`, `build_workflow_graph`, node implementations
- Graph state: `AgentState` and `build_state_type()` (graph-private, not public API)
- Routing: `EmbeddingRouter`, `ComplexityEstimator`, `PostgresRoutingStore`
- Capability gate: `CapabilityGate`, `PostgresCapabilityOverrideStore` (implementation; types are in ze-agents)
- OpenRouter client: `OpenRouterClient` (HTTP implementation)
- Embeddings: `get_embedder()` singleton
- Telemetry: `CostTracker`, `CostReconciler`, `PostgresCostStore`, telemetry context vars
- DI container: `Container`, `from_config()`, `_resolve()`
- Message store: `PostgresMessageStore` in `ze_core/conversation/` (see `specs/core/09-conversation.md`)
- Conversation helpers: `invoke_raw_turn`, `resume_turn` in `ze_core/conversation/turn.py`

**Imports from ze-agents:** `AgentContext`, `AgentResult`, `ToolCall`, `GateDecision`, `Mode`, `BaseAgent`, `ZePlugin`, `AppInterface`, `get_agent` (registry read), `registered_tools` (tool registry read), `ZeError` hierarchy.

**Does NOT include:** `BaseAgent`, `@agent`, `@tool`, `ZePlugin`, `ProactiveScheduler`, any Channel or AppInterface definition.

### `ze-sdk` — The Plugin Author's Entry Point (Phase 48, revised)

A thin re-export layer that depends on ze-agents + ze-proactive + ze-memory. Plugin packages list only `ze-sdk` as their ze dependency; they never import `ze-core` directly.

---

## Dependency Graph (Before → After)

### Before

```
ze-browser      (no ze deps)
ze-core         (no ze deps) ← contains everything
ze-notifications(no ze deps)
ze-components   (no ze deps)
ze-google       (no ze deps)
ze-memory     → ze-core
ze-personal   → ze-core, ze-memory
ze-email      → ze-core, ze-google, ze-personal
ze-prospecting→ ze-core, ze-browser, ze-personal
ze-calendar   → ze-core, ze-google, ze-personal
ze-news       → ze-core
ze-api        → ze-core, ze-memory, (all plugins)
```

### After

```
ze-browser      (no ze deps)
ze-notifications(no ze deps)
ze-components   (no ze deps)
ze-google       (no ze deps)

ze-agents       (no ze deps)            ← NEW: developer API, types, contracts
ze-proactive  → ze-agents               ← NEW: job framework
ze-memory     → ze-agents               ← was: ze-memory → ze-core
ze-core       → ze-agents               ← INVERTED: engine imports developer contracts

ze-sdk        → ze-agents, ze-proactive, ze-memory  ← NEW: plugin entry point

ze-personal   → ze-sdk                  ← was: ze-core, ze-memory
ze-email      → ze-sdk, ze-google       ← was: ze-core, ze-google, ze-personal
ze-prospecting→ ze-sdk, ze-browser      ← was: ze-core, ze-browser, ze-personal
ze-calendar   → ze-sdk, ze-google       ← was: ze-core, ze-google, ze-personal
ze-news       → ze-sdk                  ← was: ze-core

ze-api        → ze-core, ze-sdk, (all plugins)
```

The key inversion: ze-core now imports from ze-agents. Ze-core is the engine; ze-agents defines the contracts the engine honors.

---

## The Dependency Inversion in Detail

The hard coupling identified in the dependency audit is the shared type layer: `AgentContext`, `AgentResult`, `ToolCall`, `GateDecision`, `Mode`. These are imported by both graph nodes (engine) and `BaseAgent` (developer API).

**Resolution:** These types move to ze-agents. Ze-core's graph nodes import them from ze-agents.

```
Before:
  ze_core/orchestration/types.py  defines AgentContext, AgentResult, ToolCall
  ze_core/orchestration/nodes/    imports from ze_core.orchestration.types
  ze_core/orchestration/base_agent.py imports from ze_core.orchestration.types

After:
  ze_agents/types.py              defines AgentContext, AgentResult, ToolCall
  ze_core/orchestration/nodes/    imports from ze_agents.types        ← engine imports contracts
  ze_agents/base_agent.py         imports from ze_agents.types        ← dev API uses same contracts
```

Same for `GateDecision` and `Mode`:

```
Before:
  ze_core/capability/types.py     defines GateDecision, Mode
  ze_core/capability/gate.py      imports from ze_core.capability.types (implementation)
  ze_core/orchestration/base_agent.py imports from ze_core.capability.types (developer API)

After:
  ze_agents/types.py              defines GateDecision, Mode
  ze_core/capability/gate.py      imports from ze_agents.types        ← engine implements against
  ze_agents/base_agent.py         imports from ze_agents.types        ← developer uses same types
```

The agent class registry also inverts. `@agent` and `register_instance` move to ze-agents. Ze-core's container and router read the registry from ze-agents at runtime.

---

## What Moves Where

### To `ze-agents`

| Current path | New path |
|---|---|
| `ze_core/orchestration/base_agent.py` | `ze_agents/base_agent.py` |
| `ze_core/orchestration/registry.py` | `ze_agents/registry.py` |
| `ze_core/orchestration/tool.py` | `ze_agents/tool.py` |
| `ze_core/orchestration/types.py` | `ze_agents/types.py` |
| `ze_core/orchestration/hooks.py` | `ze_agents/hooks.py` |
| `ze_core/orchestration/delegate.py` | `ze_agents/delegate.py` |
| `ze_core/capability/types.py` | `ze_agents/types.py` (merged) |
| `ze_core/plugin.py` | `ze_agents/plugin.py` |
| `ze_core/interface/base.py` | `ze_agents/interface/base.py` |
| `ze_core/interface/types.py` | `ze_agents/interface/types.py` |
| `ze_core/interface/validation.py` | `ze_agents/interface/validation.py` |
| `ze_core/channels/base.py` | `ze_agents/channels/base.py` |
| `ze_core/channels/types.py` | `ze_agents/channels/types.py` |
| `ze_core/channels/registry.py` | `ze_agents/channels/registry.py` |
| `ze_core/progress/reporter.py` | `ze_agents/progress/reporter.py` |
| `ze_core/progress/translations.py` | `ze_agents/progress/translations.py` |
| `ze_core/errors.py` | `ze_agents/errors.py` |
| `ze_core/logging.py` | `ze_agents/logging.py` |
| `ze_core/settings.py` | `ze_agents/settings.py` |
| `ze_core/defaults.py` | `ze_agents/defaults.py` |

> **Later moves:** Phase 64 extracted `ZePlugin`, channels, and signals into
> `ze-plugin` (not `ze-agents`). Phase 77 extracted logging into `ze-logging`
> (replacing `ze_agents/logging.py`).

### To `ze-proactive`

| Current path | New path |
|---|---|
| `ze_core/proactive/job.py` | `ze_proactive/job.py` |
| `ze_core/proactive/scheduler.py` | `ze_proactive/scheduler.py` |
| `ze_core/proactive/notifier.py` | `ze_proactive/notifier.py` |
| `ze_core/proactive/push_log_store.py` | `ze_proactive/push_log_store.py` |

### Stays in `ze-core`

| Path | Why |
|---|---|
| `ze_core/orchestration/graph.py` | Engine internals |
| `ze_core/orchestration/nodes/` | Engine internals |
| `ze_core/orchestration/edges.py` | Engine internals |
| `ze_core/orchestration/state.py` | Graph-private state schema |
| `ze_core/routing/` | Engine routing infrastructure |
| `ze_core/capability/gate.py` | Gate implementation (types move to ze-agents) |
| `ze_core/capability/overrides.py` | Gate persistence (engine concern) |
| `ze_core/openrouter/` | HTTP client implementation |
| `ze_core/embeddings.py` | Embedder singleton (used by routing) |
| `ze_core/telemetry/` | Cost tracking (engine concern) |
| `ze_core/container.py` | DI engine |
| `ze_core/conversation/turn.py` | Turn invocation helpers |

### Moves to `ze-api`

| Path | Why |
|---|---|
| `ze_core/conversation/messages/store.py` | Conversation message persistence |

---

## `BaseAgent` and the Embedder — a Special Case

`base_agent.py` currently imports `ze_core.embeddings` (the SentenceTransformer singleton) for internal routing-hint computation. If `base_agent` moves to ze-agents and ze-agents cannot import ze-core (to avoid a cycle), this import must be severed.

The correct resolution: `BaseAgent` should not call the embedder. The routing node in ze-core's engine handles all embedding. Any routing-hint computation in `BaseAgent` that calls the embedder is misplaced and should be moved to the routing node, or the embedding should be injected as a callable through `AgentContext` rather than imported as a global.

This is a design fix forced by the split — and a correct one. An agent's job is to respond, not to embed its own routing hints.

---

## Package Configuration

```toml
# core/ze-agents/pyproject.toml
[project]
name = "ze-agents"
version = "0.1.0"
description = "Ze developer API — BaseAgent, @agent, @tool, ZePlugin, shared types"
requires-python = ">=3.11"
dependencies = []   # no ze deps — this is the base layer

# core/ze-proactive/pyproject.toml
[project]
name = "ze-proactive"
version = "0.1.0"
description = "Ze job scheduling and notification framework"
requires-python = ">=3.11"
dependencies = ["ze-agents"]

# core/ze-core/pyproject.toml (updated)
[project]
name = "ze-core"
version = "0.1.0"
description = "Ze orchestration engine — graph, routing, container, capability gate"
requires-python = ">=3.11"
dependencies = ["ze-agents", "ze-memory", ...]   # engine imports developer contracts

# packages/ze-sdk/pyproject.toml (revised from phase 48)
[project]
name = "ze-sdk"
version = "0.1.0"
description = "Public API surface for Ze plugin development"
requires-python = ">=3.11"
dependencies = ["ze-agents", "ze-proactive", "ze-memory"]
```

---

## Migration Path

### Step 1: Create ze-agents

Extract the modules listed above into a new `core/ze-agents/` package. Add import aliases in ze-core pointing to the new locations so nothing breaks mid-migration:

```python
# ze_core/orchestration/base_agent.py (temporary shim)
from ze_agents.base_agent import BaseAgent  # noqa: F401 — compatibility shim
```

### Step 2: Update ze-core imports

Replace all `from ze_core.orchestration.types import ...` inside ze-core's engine files with `from ze_agents.types import ...`. Same for `base_agent`, `registry`, `tool`, `errors`, `logging`.

### Step 3: Create ze-proactive

Move `ze_core/proactive/` to `core/ze-proactive/ze_proactive/`. Update imports in ze-core (container, graph) that reference the old paths. Add compatibility shims in ze-core.

### Step 4: Update ze-memory

Replace `from ze_core.* import ...` in ze-memory with `from ze_agents.* import ...`. Ze-memory's dependency list changes from `ze-core` to `ze-agents`.

### Step 5: Update all plugins

Replace `from ze_core.*` with `from ze_sdk.*` (or `from ze_agents.*` / `from ze_proactive.*` if not using ze-sdk). Update plugin `pyproject.toml` deps.

### Step 6: Remove compatibility shims

Once all dependents are updated, delete the temporary re-export shims from ze-core.

---

## Revised Phase 48 (ze-sdk)

Phase 48's ze-sdk spec described ze-sdk as re-exporting from ze-core. After this split, ze-sdk re-exports from ze-agents, ze-proactive, and ze-memory instead. Ze-core is never a ze-sdk dependency. The re-export table in phase 48 is unchanged; only the source packages differ.

---

## Benefits

**Plugin authoring becomes lighter.** A new plugin lists `ze-sdk` as its dependency. It transitively pulls in ze-agents + ze-proactive + ze-memory. Ze-core's engine (LangGraph, routing, embedding model, asyncpg pools) is not a transitive dependency of plugin packages. Plugin tests don't load the engine.

**Ze-core can evolve freely.** Graph node implementations, routing algorithms, checkpointer wiring — all of these can change without any plugin noticing, because plugins don't import from ze-core.

**The developer API is stable by definition.** Ze-agents makes an explicit commitment: its public exports don't change without a version bump. Ze-core makes no such commitment.

**Proactive jobs are testable in isolation.** Ze-proactive has no engine dependency. A job can be unit-tested by constructing `ProactiveJob` and mocking `AppInterface`, with no LangGraph graph, no router, no asyncpg pool in scope.

---

## Implementation Notes

- The split can be done incrementally. Compatibility shims allow the old import paths to keep working during the transition, so ze-api and existing plugins don't need to be updated atomically.
- The `ze_core.orchestration.state.AgentState` is graph-private. It does NOT move to ze-agents. Plugins must not depend on `AgentState` directly — they interact with the state machine through `ZePlugin` hooks (which receive only the data they need). Any plugin file that currently imports `AgentState` is doing something it shouldn't.
- `ze_core.defaults.MODEL_WORKFLOW_VERIFY` currently imported in ze-personal must be moved to settings before the split, so ze-personal doesn't end up depending on ze-core for one constant.
- `ze_core.db.DBPool` type alias should move to ze-api — it's a convenience alias for `asyncpg.Pool` that only matters at the app level.

---

## Open Questions

- [ ] **Embedder in BaseAgent.** `base_agent.py` currently imports the embedder. Confirm whether this is routing-hint embedding (belongs in the routing node) or something else. Resolve before implementing the split — this is the main risk of a circular dependency.
- [ ] **OpenRouter client in ze-agents.** `BaseAgent` references `OpenRouterClient` in type annotations (for `self.agentic_loop(client=...)`). Since ze-agents has no ze deps, `OpenRouterClient` must either (a) be extracted to a standalone `ze-openrouter` package that ze-agents depends on, or (b) be referenced via a `Protocol` in ze-agents so the type annotation works without the concrete class. Option (b) is lower churn.
- [ ] **Settings split.** `ze_core.settings.Settings` contains both base settings (DATABASE_URL, OPENROUTER_API_KEY) and app-level settings that only ze-api cares about. Before the split, extract a `BaseSettings` (in ze-agents, no ze deps) from which `ze_api.settings.Settings` inherits. Plugins type-annotate against `BaseSettings`.
- [ ] **Compatibility shim lifetime.** How long do ze-core re-export shims stay? Suggest: one full release cycle — shims are tagged deprecated at split, removed in the next phase. For a single-developer repo, "one sprint after all plugins are updated" is sufficient.
- [x] **`ze_core.conversation` module.** `PostgresMessageStore`, session store, and `PendingConfirmationStore` live in `ze_core/conversation/` with migrations `zc015`–`zc018`. Resolved: stores stay in ze-core; ze-api is transport only.
