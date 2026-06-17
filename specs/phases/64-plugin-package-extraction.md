# ze-plugin Package Extraction — Spec

> **Package:** `ze_plugin` (new) · `ze_agents` (trimmed)
> **Phase:** 64
> **Status:** Pending

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze-plugin` package scaffold | 🔲 Pending |
| Move `ZePlugin` + registry | 🔲 Pending |
| Move `ZeIntegration` protocol | 🔲 Pending |
| Move `SignalSource` protocol | 🔲 Pending |
| Move `channels/` subpackage | 🔲 Pending |
| Trim `ze-agents` | 🔲 Pending |
| Update `ze-sdk` re-exports | 🔲 Pending |
| Update `ze-core` imports | 🔲 Pending |
| Update all plugin imports | 🔲 Pending |
| Update `ze-api` imports | 🔲 Pending |
| Tests green | 🔲 Pending |

---

## Purpose

`ze-agents` accumulated four distinct responsibilities over phases 47–63:

1. **Agent execution runtime** — `BaseAgent`, agentic loop, harness hooks, delegation
2. **Registration surface** — `@agent`, `@tool` decorators, `AgentRegistry`
3. **Plugin extension framework** — `ZePlugin`, `DataDomain`, `ZeIntegration`, `SignalSource`, `channels/`
4. **Shared primitives** — `LLMClient`, `DBPool`, errors, types, settings

Responsibilities 1–2 are cohesive: they are the developer API for *building* agents. Responsibility 3 is the plugin system — the extension point for *wiring* domain packages into the engine. These are different audiences with different change rates.

This phase extracts the plugin framework into a new `ze-plugin` package, leaving `ze-agents` as the focused developer API for agent authors.

---

## Responsibilities

### ze-plugin (new)

- `ZePlugin` ABC — the single extension point for domain packages
- Plugin registry — `_registry`, `get_plugin_registry()`, `__init_subclass__` wiring
- `DataDomain` — data export/import/delete descriptor
- `ZeIntegration` protocol — credential class contract for `integration_types()`
- `SignalSource` protocol — plugin-provided signal contributor for the admission pipeline
- `channels/` — `Channel` ABC, `ChannelRegistry`, channel types (`ChannelType`, `Message`, etc.)

### ze-agents (trimmed)

Everything currently in `ze-agents` that is NOT in the above list stays:

- `BaseAgent` ABC + agentic loop
- `@agent` decorator + `AgentRegistry`
- `@tool` decorator + `ToolAccess`
- `LLMClient`, `DBPool` protocols
- `HarnessHook` ABC + hook registry (agentic loop concern — not a plugin concern)
- `AppInterface` ABC + `InputPreprocessor`
- `ProgressReporter` + `ProgressTranslations`
- `AgentDelegate`
- `errors.py`, `types.py`, `settings.py`, `defaults.py`, `logging.py`, `tasks.py`

---

## Out of Scope

- `ze-onboarding` — already a separate package; `ZePlugin.onboarding()` is unaffected
- `ze-proactive` — unchanged
- `ze-memory` — unchanged
- `ze-sdk` interface — the `ze_sdk.*` import surface for plugin authors stays identical;
  only the re-export targets change internally
- Any behavioural changes — this is a pure structural refactor; no logic moves

---

## Module Location

```
core/
├── ze-agents/              # trimmed — agent execution + developer API only
│   └── ze_agents/
│       ├── base_agent.py
│       ├── client.py
│       ├── db.py
│       ├── defaults.py
│       ├── delegate.py
│       ├── errors.py
│       ├── hooks.py
│       ├── interface/
│       ├── logging.py
│       ├── progress/
│       ├── registry.py
│       ├── settings.py
│       ├── tasks.py
│       ├── tool.py
│       └── types.py
└── ze-plugin/              # new — plugin extension framework
    └── ze_plugin/
        ├── __init__.py
        ├── channels/
        │   ├── __init__.py
        │   ├── base.py         # Channel ABC
        │   ├── registry.py     # ChannelRegistry
        │   └── types.py        # ChannelType, Message, SentMessage, Thread, …
        ├── integration.py      # ZeIntegration protocol
        ├── plugin.py           # ZePlugin ABC + DataDomain
        ├── registry.py         # _registry, get_plugin_registry()
        └── signals.py          # SignalSource protocol
```

---

## Interface Contract

### ZePlugin dependency direction

`ze-plugin` depends on `ze-agents` (not the other way around). `ZePlugin.agents()` returns
`list[type[BaseAgent]]` and `pre_route_node()` returns a callable — both reference types
from `ze-agents`. This is the only cross-package reference.

```python
# ze_plugin/plugin.py
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ze_agents.base_agent import BaseAgent
```

No circular imports: `ze-agents` never imports from `ze-plugin`.

### Public API (unchanged for callers)

Plugin authors import via `ze_sdk` — those import paths are not affected:

```python
from ze_sdk import ZePlugin, BaseAgent, agent, tool   # unchanged
from ze_sdk.channels import Channel, ChannelType       # unchanged
from ze_sdk.memory import SignalSource                 # unchanged
```

Only the *re-export targets* inside `ze_sdk` change.

---

## Updated Dependency Graph

```
ze-browser      (no ze deps)
ze-agents       (no ze deps)                           ← trimmed
ze-plugin     → ze-agents                             ← new
ze-proactive  → ze-agents
ze-notifications(no ze deps)
ze-components   (no ze deps)
ze-memory     → ze-agents
ze-eval         (no ze deps — HTTP only)
ze-sdk        → ze-agents, ze-plugin, ze-proactive, ze-memory
ze-core       → ze-agents, ze-plugin                  ← adds ze-plugin
ze-google       (no ze deps)
ze-personal   → ze-sdk
ze-email      → ze-sdk, ze-google, ze-personal
ze-prospecting→ ze-sdk, ze-browser, ze-personal
ze-calendar   → ze-sdk, ze-google, ze-personal
ze-news       → ze-sdk
ze-api        → ze-core, ze-sdk, ze-personal, ze-email, ze-prospecting,
                  ze-calendar, ze-google, ze-browser, ze-news,
                  ze-notifications, ze-components
ze-web          (React — no Python deps)
```

---

## Migration Steps

These are ordered to keep the test suite green at each step.

### 1. Scaffold `ze-plugin`

Create `core/ze-plugin/` with `pyproject.toml` declaring a dependency on `ze-agents`.
Empty `ze_plugin/__init__.py`. No behaviour yet.

### 2. Move `channels/`

Copy `ze_agents/channels/` → `ze_plugin/channels/`. Add re-export shim in
`ze_agents/channels/__init__.py` importing from `ze_plugin.channels` (keeps existing
consumers working during the migration window).

### 3. Move `signals.py` and `integration.py`

Same pattern: move, add shims in old locations.

### 4. Move `plugin.py` and registry

Move `ze_agents/plugin.py` → `ze_plugin/plugin.py`.
Move `ze_agents/plugin._registry` logic → `ze_plugin/registry.py`.
Shim `ze_agents/plugin.py` to re-export from `ze_plugin.plugin`.

### 5. Update `ze-sdk` re-exports

Update `ze_sdk/__init__.py`, `ze_sdk/channels.py`, `ze_sdk/memory.py` to import
from `ze_plugin.*` instead of `ze_agents.*`. Add `ze-plugin` to `ze-sdk`
dependencies.

### 6. Update `ze-core` imports

`ze_core/__init__.py`, `ze_core/orchestration/graph.py`,
`ze_core/orchestration/state.py` — replace `ze_agents.plugin`, `ze_agents.channels`,
`ze_agents.signals` with `ze_plugin.*`.

### 7. Update `ze-api` imports

`ze_api/bootstrap.py`, `ze_api/container.py`, `ze_api/data/service.py`,
`ze_api/migrate.py`.

### 8. Update plugin imports

Each plugin (`ze-personal`, `ze-email`, `ze-calendar`, `ze-prospecting`, `ze-news`)
— check whether they import directly from `ze_agents.*` or via `ze_sdk.*`.
Direct imports must be updated; `ze_sdk.*` imports are already correct after step 5.

### 9. Remove shims

Delete the re-export shims added in steps 2–4. Run full test suite.

### 10. Verify `ze-agents` has no `ze_plugin` dep in pyproject.toml

Confirm the dependency arrow is one-directional: `ze-plugin → ze-agents`, never reversed.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `BaseAgent` type reference in `ZePlugin.agents()`; `HarnessHook` types in event payloads |

---

## Implementation Notes

- Shims in steps 2–4 exist only during the migration window. Remove them in step 9.
  They should not be committed to `main` permanently — they mask the structural split.
- `ze-agents` `pyproject.toml` must NOT gain a `ze-plugin` dependency at any point.
  If a test or import requires it, the abstraction boundary is wrong and must be fixed.
- `ze_sdk/memory.py` currently re-exports `SignalSource` from `ze_agents.signals`.
  After step 5 it re-exports from `ze_plugin.signals`. Caller import paths are unchanged.

---

## Open Questions

- [x] Should `HarnessHook` move to `ze-plugin`? **No** — hooks fire inside the agentic
  loop, which is `BaseAgent`'s concern. They are not a plugin extension point; plugins
  register hooks via `plugin.startup()` calling `register_hook()`, not by subclassing.
- [x] Should `channels/` move to a standalone `ze-channels` package? **No** — channels
  are semantically part of the plugin surface (`ZePlugin.channels()` declares them). A
  separate package adds a dep level without gaining cohesion.
- [x] Does `ze-onboarding` need any changes? **No** — it is already separate and
  `ZePlugin.onboarding()` already imports from `ze_onboarding`.
