# Ze SDK — Spec

> **Package:** `ze-sdk` (`core/ze-sdk/`)
> **Phase:** 49
> **Status:** Done
> **Prerequisite:** Phase 48 (ze-core split into ze-agents + ze-proactive) must be complete first.

---

## Purpose

After Phase 48, Ze's developer surface lives in several core packages: `ze-agents`
(authoring API and shared types), `ze-proactive` (job framework), `ze-memory`
(memory retrieval), and `ze-onboarding` (setup providers). A plugin author still needs
to know which symbols live in which package, and must list multiple dependencies
explicitly.

`ze-sdk` removes that friction. It is a flat re-export layer over ze-agents,
ze-proactive, ze-memory, and ze-onboarding. Plugin authors import from `ze_sdk.*`
and never think about which underlying package a symbol comes from. A plugin's only Ze
dependency is `ze-sdk`.

Ze-core (the engine) is never a ze-sdk dependency. Plugins cannot transitively
import the LangGraph engine, embedding model, asyncpg pool wiring, or routing
infrastructure. Ze-core can evolve those internals freely.

---

## Responsibilities

- Re-export every symbol a plugin author legitimately needs under a clean,
  grouped namespace (`ze_sdk`, `ze_sdk.types`, `ze_sdk.proactive`, `ze_sdk.channels`,
  `ze_sdk.memory`, `ze_sdk.onboarding`, `ze_sdk.errors`).
- Hold no business logic — no implementations, no new types, no monkey-patching.
  Every export is a direct re-export from ze-agents, ze-proactive, ze-memory, or
  ze-onboarding.
- Serve as the single Ze dependency for plugin packages. Plugins list `ze-sdk`;
  the transitive graph pulls in ze-agents, ze-proactive, ze-memory, and ze-onboarding. Ze-core
  never appears.
- Make the stable surface explicit: what ze-sdk re-exports is what ze-agents and
  ze-proactive commit to keeping stable. Ze-core's internals are not part of that
  commitment.

---

## Out of Scope

- Does not replace ze-agents or ze-proactive — no implementations live here.
- Does not vendor or duplicate types. `ze_sdk.AgentContext is ze_agents.types.AgentContext`
  must be true.
- Does not cover domain types from `ze_personal` (PersonStore, GoalStore, etc.) —
  those are domain implementations, not SDK.
- Does not re-export `ze_google` or `ze_browser` — those remain separate optional
  dependencies that plugins declare if they need them.
- Does not wrap `ze_api` or anything in `apps/`.
- Does not re-export ze-core engine internals (graph, routing, container, telemetry).

---

## Module Location

```
core/ze-sdk/
  pyproject.toml
  ze_sdk/
    __init__.py    ← plugin root: ZePlugin, @agent, @tool, BaseAgent, ToolAccess, get_logger, Settings
    types.py       ← execution types: AgentContext, AgentResult, ToolCall, GateDecision, Mode, Action, Notification
    proactive.py   ← job framework: ProactiveJob, proactive_job, ProactiveScheduler, ProactiveNotifier, PushLogStore
    channels.py    ← channel contract: Channel, ChannelType, ChannelHandle, Message, SentMessage, Thread, ThreadMessage
    memory.py      ← memory view: MemoryContext, MemoryStore, Fact, Episode, Procedure, Entity, TaskState, RetrievalRequest
    onboarding.py  ← setup API: OnboardingProvider, OnboardingStep, OnboardingSeed, OnboardingResult
    errors.py      ← full ZeError hierarchy
```

---

## Public API

### `ze_sdk` (root)

```python
from ze_plugin.plugin import ZePlugin
from ze_agents.registry import agent
from ze_agents.tool import tool, ToolAccess
from ze_agents.base_agent import BaseAgent
from ze_logging import get_logger
from ze_agents.settings import Settings

__all__ = [
    "ZePlugin",
    "agent",
    "tool",
    "ToolAccess",
    "BaseAgent",
    "get_logger",
    "Settings",
]
```

`OpenRouterClient` is not re-exported. Agents receive an LLM client via constructor
injection typed against `LLMClient` (a Protocol defined in ze-agents). The concrete
`OpenRouterClient` is a ze-core implementation detail.

### `ze_sdk.types`

```python
from ze_agents.types import (
    AgentContext,
    AgentResult,
    ToolCall,
    GateDecision,
    Mode,
    AbortToken,
)
from ze_agents.interface.types import Action, Notification

__all__ = [
    "AgentContext",
    "AgentResult",
    "ToolCall",
    "GateDecision",
    "Mode",
    "AbortToken",
    "Action",
    "Notification",
]
```

`AgentState` is deliberately excluded — it is graph-private state owned by ze-core.
Plugins interact with the state machine only through `ZePlugin` hooks
(`state_extensions`, `pre_route_node`, `graph_nodes`) which receive only the
data they need. Any plugin that currently imports `AgentState` is doing something it
shouldn't.

### `ze_sdk.proactive`

```python
from ze_proactive.job import ProactiveJob, proactive_job
from ze_proactive.scheduler import ProactiveScheduler
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore, PushLogEntry

__all__ = [
    "ProactiveJob",
    "proactive_job",
    "ProactiveScheduler",
    "ProactiveNotifier",
    "PushLogStore",
    "PushLogEntry",
]
```

### `ze_sdk.channels`

```python
from ze_agents.channels.base import Channel
from ze_agents.channels.types import (
    ChannelType,
    ChannelHandle,
    Message,
    SentMessage,
    Thread,
    ThreadMessage,
)
from ze_agents.errors import ChannelSendError

__all__ = [
    "Channel",
    "ChannelType",
    "ChannelHandle",
    "Message",
    "SentMessage",
    "Thread",
    "ThreadMessage",
    "ChannelSendError",
]
```

### `ze_sdk.memory`

```python
from ze_memory.types import (
    MemoryContext,
    Fact,
    Episode,
    Procedure,
    Entity,
    TaskState,
    RetrievalRequest,
)
from ze_memory.store import MemoryStore
from ze_memory.retriever import PostgresMemoryStore

__all__ = [
    "MemoryContext",
    "Fact",
    "Episode",
    "Procedure",
    "Entity",
    "TaskState",
    "RetrievalRequest",
    "MemoryStore",
    "PostgresMemoryStore",
]
```

`PostgresMemoryStore` is re-exported because plugin constructors today type-annotate
it directly (e.g. `PersonalPlugin.__init__` takes `memory_store: PostgresMemoryStore`).
Once the full DI refactor from phase 47 lands and plugins receive `MemoryStore` (the
ABC), the concrete type can be removed from the SDK.

### `ze_sdk.errors`

```python
from ze_agents.errors import (
    ZeCoreError,
    RoutingError,
    InvalidPromptError,
    AgentError,
    AgentTimeoutError,
    UnknownAgentError,
    AgentConfigError,
    AgentAbortedError,
    HookAbort,
    InterfaceError,
    InterfaceConfigError,
    CapabilityError,
    ToolBlockedError,
    UnknownToolError,
    WorkflowError,
    WorkflowPlanError,
    WorkflowExecutionError,
    GoalError,
    GoalPlanError,
    GoalExecutionError,
    PersonaError,
    UnknownProfileError,
    UnknownDialError,
    ChannelError,
    ChannelNotFoundError,
    ChannelSendError,
)

__all__ = [
    "ZeCoreError",
    "RoutingError",
    "InvalidPromptError",
    "AgentError",
    "AgentTimeoutError",
    "UnknownAgentError",
    "AgentConfigError",
    "AgentAbortedError",
    "HookAbort",
    "InterfaceError",
    "InterfaceConfigError",
    "CapabilityError",
    "ToolBlockedError",
    "UnknownToolError",
    "WorkflowError",
    "WorkflowPlanError",
    "WorkflowExecutionError",
    "GoalError",
    "GoalPlanError",
    "GoalExecutionError",
    "PersonaError",
    "UnknownProfileError",
    "UnknownDialError",
    "ChannelError",
    "ChannelNotFoundError",
    "ChannelSendError",
]
```

---

## Package Configuration

```toml
# core/ze-sdk/pyproject.toml

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ze-sdk"
version = "0.1.0"
description = "Public API surface for Ze plugin development"
requires-python = ">=3.11"
dependencies = [
    "ze-agents",
    "ze-proactive",
    "ze-memory",
    "ze-onboarding",
]

[tool.uv.sources]
ze-agents    = { workspace = true }
ze-proactive = { workspace = true }
ze-memory    = { workspace = true }
ze-onboarding = { workspace = true }

[tool.hatch.build.targets.wheel]
packages = ["ze_sdk"]
```

Plugin packages replace their `ze-core`, `ze-memory` direct dependencies with `ze-sdk`:

```toml
# Before (e.g. plugins/ze-calendar/pyproject.toml)
dependencies = ["ze-core", "ze-google", "ze-personal", ...]

# After
dependencies = ["ze-sdk", "ze-google", "ze-personal", ...]
```

---

## Dependency Graph

```
ze-agents       (no ze deps)
ze-onboarding   (no ze deps)
ze-proactive  → ze-agents
ze-memory     → ze-agents
ze-sdk        → ze-agents, ze-proactive, ze-memory, ze-onboarding   ← plugin entry point

ze-personal   → ze-sdk
ze-email      → ze-sdk, ze-google
ze-prospecting→ ze-sdk, ze-browser
ze-calendar   → ze-sdk, ze-google
ze-news       → ze-sdk

ze-core       → ze-agents                            ← engine; never a plugin dep
ze-api        → ze-core, ze-sdk, all plugins
```

Ze-core does not appear in any plugin's dependency list. Ze-api imports from ze-core
directly for engine internals (container, graph construction, routing).

---

## Migration: Updating Plugin Imports

Every `from ze_core.*` and `from ze_memory.*` import in plugin code is replaced with
a `ze_sdk` equivalent:

| Before | After |
|--------|-------|
| `from ze_core.plugin import ZePlugin` | `from ze_sdk import ZePlugin` |
| `from ze_core.orchestration.registry import agent` | `from ze_sdk import agent` |
| `from ze_core.orchestration.tool import tool, ToolAccess` | `from ze_sdk import tool, ToolAccess` |
| `from ze_core.orchestration.base_agent import BaseAgent` | `from ze_sdk import BaseAgent` |
| `from ze_core.logging import get_logger` | `from ze_sdk import get_logger` |
| `from ze_core.settings import Settings` | `from ze_sdk import Settings` |
| `from ze_core.orchestration.types import AgentContext, AgentResult, ToolCall` | `from ze_sdk.types import AgentContext, AgentResult, ToolCall` |
| `from ze_core.capability.types import GateDecision, Mode` | `from ze_sdk.types import GateDecision, Mode` |
| `from ze_core.interface.types import Action, Notification` | `from ze_sdk.types import Action, Notification` |
| `from ze_core.proactive.job import ProactiveJob, proactive_job` | `from ze_sdk.proactive import ProactiveJob, proactive_job` |
| `from ze_core.proactive.scheduler import ProactiveScheduler` | `from ze_sdk.proactive import ProactiveScheduler` |
| `from ze_core.proactive.notifier import ProactiveNotifier` | `from ze_sdk.proactive import ProactiveNotifier` |
| `from ze_core.proactive.push_log_store import PushLogStore, PushLogEntry` | `from ze_sdk.proactive import PushLogStore, PushLogEntry` |
| `from ze_core.channels.base import Channel` | `from ze_sdk.channels import Channel` |
| `from ze_core.channels.types import ChannelType, Message, ...` | `from ze_sdk.channels import ChannelType, Message, ...` |
| `from ze_memory.types import MemoryContext, Fact, ...` | `from ze_sdk.memory import MemoryContext, Fact, ...` |
| `from ze_memory.store import MemoryStore` | `from ze_sdk.memory import MemoryStore` |
| `from ze_memory.retriever import PostgresMemoryStore` | `from ze_sdk.memory import PostgresMemoryStore` |
| `from ze_core.errors import GoalPlanError, ...` | `from ze_sdk.errors import GoalPlanError, ...` |

`from ze_core.openrouter.client import OpenRouterClient` has no ze_sdk equivalent.
Agents that type-annotate against `OpenRouterClient` should switch to the `LLMClient`
Protocol defined in ze-agents (`from ze_agents.client import LLMClient`).

---

## What Is Not Re-Exported

These are engine internals that plugin authors should never import:

| Symbol | Why |
|--------|-----|
| `ze_core.orchestration.graph` | Graph build internals; plugins use `ZePlugin.graph_nodes()` hooks |
| `ze_core.orchestration.state.AgentState` | Graph-private; plugins never read raw graph state |
| `ze_core.orchestration.state.build_state_type()` | Framework internal |
| `ze_core.routing.*` | Routing internals; plugins interact via `description` and `intent_map` |
| `ze_core.capability.gate` / `overrides` | Gate implementation; types (GateDecision, Mode) are in ze-agents |
| `ze_core.container.*` | App-level DI; not a plugin concern |
| `ze_core.db.*` | DB pool management belongs in ze-api |
| `ze_core.telemetry.*` | Cost tracking is engine-internal; plugins do not instrument themselves |
| `ze_core.openrouter.*` | Concrete HTTP client; use LLMClient Protocol in ze-agents |
| `ze_agents.base_agent._truncate_messages` | Private helper, no public contract |

---

## Implementation Notes

- All `__init__.py` / module files in `ze_sdk` are `from X import Y` only — no
  `class`, `def`, or logic of any kind. Any symbol that seems useful should be
  added to ze-agents or ze-proactive and re-exported here.
- `ze_sdk.telemetry` is removed from the SDK (it appeared in the original spec).
  `set_agent_context` and `set_flow_context` are engine-level instrumentation hooks
  that belong in ze-core. Plugin authors do not call them directly.
- `MODEL_WORKFLOW_VERIFY` and other `ze_core.defaults.*` constants currently imported
  in ze-personal must be moved to `Settings` (or into the plugin itself as local
  constants) before the plugin migration step.

---

## CLAUDE.md and Docs Impact

- `CLAUDE.md` "Adding a new agent" section: update all import examples to `ze_sdk`.
- `CLAUDE.md` package dependency graph: add ze-agents, ze-proactive, ze-sdk rows;
  update plugin rows to show `ze-sdk` instead of `ze-core, ze-memory`.
- `docs/adding-an-agent.md`: all code examples switch to `ze_sdk` imports.
- Each plugin's `pyproject.toml`: replace `ze-core` (and `ze-memory` if listed) with `ze-sdk`.

---

## Open Questions

- [ ] **`ze_sdk.logging` vs root-level `get_logger`**: `from ze_sdk.logging import get_logger`
  may confuse tools expecting stdlib `logging`. Options: (a) expose via root
  (`from ze_sdk import get_logger`) and omit the `logging` submodule, or (b) keep the
  submodule but document the clash. Lean toward (a) — `get_logger` is a single symbol
  and deserves root placement alongside `agent`, `tool`, `BaseAgent`.
- [ ] **`ze_google` and `ze_browser` optional extras**: Should ze-sdk offer
  `ze-sdk[google]` and `ze-sdk[browser]` extras that pull in those optional packages?
  Lean toward no — those packages are optional and only used by specific plugins.
  Keeping them as separate declared deps makes the requirement explicit.
- [ ] **`ze_core.db.DBPool` in ze-personal**: Used for raw pool access. Once phase 47's
  full DI lands and plugins receive `asyncpg.Pool` directly from `_resolve()`, this
  import disappears. Defer exposing it in ze-sdk until then.
