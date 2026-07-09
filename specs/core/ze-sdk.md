# ze-sdk — Plugin Entry Point

> **Package:** `core/ze-sdk` — `ze_sdk/`
> **Status:** Done
> **Implemented in:** [Phase 49](../phases/049-ze-sdk/spec.md)

---

## Purpose

Flat re-export layer. Plugin authors import everything they need from `ze_sdk.*` and
never import from internal packages (`ze_agents`, `ze_plugin`, `ze_core`, `ze_proactive`,
`ze_communication`). The SDK is the stable public surface; internal packages can
restructure without breaking plugins.

---

## Responsibilities

- Re-export the complete plugin authoring surface as a flat, stable namespace
- Be the only Ze import a plugin ever needs (except domain packages like `ze_personal`,
  `ze_calendar`, `ze_google`)
- Document what is and isn't in-scope for plugins

---

## Out of Scope

- Implementing any functionality — all logic lives in the packages this re-exports
- Engine internals — `ze_core.*` is never re-exported here

---

## Module Location

```
core/ze-sdk/ze_sdk/
  __init__.py      ← top-level: @agent, BaseAgent, @tool, ZeError subclasses, Settings
  types.py         ← AgentContext, AgentResult, ToolCall, shared types
  errors.py        ← full ZeError hierarchy
  channels.py      ← Channel ABC, ChannelType, ChannelHandle, InboundMessage
  proactive.py     ← ProactiveJob, ProactiveScheduler
  memory.py        ← MemoryStore, FactRecord, EpisodeRecord, retrieval helpers
  automation.py    ← GoalStore, WorkflowStore, AutomationStore (read-only for plugins)
  onboarding.py    ← OnboardingCoordinator, OnboardingProvider
  ui.py            ← component descriptors, ManifestEntry
```

---

## Interface Contract

```python
# What a plugin author imports
from ze_sdk import agent, BaseAgent, tool, Settings, ZePlugin
from ze_sdk.types import AgentContext, AgentResult
from ze_sdk.errors import ZeError, AgentError, ToolError
from ze_sdk.channels import Channel, ChannelType, InboundMessage
from ze_sdk.proactive import ProactiveJob
from ze_sdk.memory import MemoryStore
from ze_sdk.automation import GoalStore, WorkflowStore
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `@agent`, `BaseAgent`, `@tool`, `LLMClient`, errors, types |
| `ze-plugin` | `ZePlugin`, `SignalSource` |
| `ze-proactive` | `ProactiveJob`, `ProactiveScheduler` |
| `ze-communication` | `Channel` ABC, channel types |
| `ze-memory` | memory read/write protocols |
| `ze-automation` | automation store contracts |
| `ze-data` | `DataDomain` |
| `ze-logging` | `get_logger` |

---

## Implementation Notes

If a plugin needs something that isn't in `ze_sdk.*`, the right answer is almost always
to add it to the SDK, not to have the plugin import the internal package directly.
The one exception is domain packages: `ze_personal`, `ze_calendar`, `ze_google` are
imported directly when a plugin builds on another plugin's domain.
