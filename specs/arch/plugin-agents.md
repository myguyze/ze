# Ze — Plugin Agent Migration

> **Status:** Done (Phase 20 / plugin framework)

## Context

Following `specs/arch/package-reorg.md` (Phase 20), domain agents were migrated out of
the monolithic `ze/` app package into `plugins/` and `core/` packages. Goal and workflow
agents now live in `ze-automation`; personal-assistant agents live in `ze-personal` and
other plugins. `bootstrap_agents()` discovers agent module paths via
`ZePlugin.agent_module_paths()` and core package helpers such as
`ze_automation.agent_module_paths()`.

---

## Goals

1. Domain agents live in their owning packages — they import from `ze_sdk` and domain
   modules, not from `ze_api`.
2. `bootstrap_agents()` accepts plugin-provided module paths; the same `_resolve()` DI
   mechanism instantiates all agents.
3. Adding a new plugin agent requires only `agent_module_paths()` on the plugin — no
   edits to ze-api bootstrap (ze-api has no bootstrap module; wiring is in
   `ze_api/container.py`).

---

## `ZePlugin.agent_module_paths()`

New optional hook in `ze_plugin/plugin.py`:

```python
@classmethod
def agent_module_paths(cls) -> list[str]:
    """Return dotted module paths to import for @agent / @tool registration."""
    return []
```

Each plugin returns paths to its tools module (first) and agent module(s). The ze-api
container collects paths from all plugins plus core packages, then calls
`ze_agents.bootstrap.import_agent_modules()`.

---

## Agent locations (current)

| Agent | Package | Module |
|-------|---------|--------|
| GoalAgent, WorkflowAgent | `ze-automation` | `ze_automation/agents/` |
| ResearchAgent, CompanionAgent | `ze-personal` | `ze_personal/agents/` |
| CalendarAgent, RemindersAgent | `ze-calendar` | `ze_calendar/agents/` |
| EmailAgent | `ze-email` | `ze_email/agents/` |
| ProspectingAgent | `ze-prospecting` | `ze_prospecting/agents/` |
| FinanceAgent | `ze-finance` | `ze_finance/agents/` |

---

## Bootstrap wiring

```python
# ze_agents/bootstrap.py
def bootstrap_agents(..., extra_module_paths: list[str] | None = None) -> None:
    ...
```

```python
# ze_api/container.py (simplified)
from ze_agents.bootstrap import bootstrap_agents, import_agent_modules
from ze_plugin.bootstrap import discover_plugins, instantiate_plugins

paths = []
for plugin in plugins:
    paths.extend(plugin.agent_module_paths())
paths.extend(ze_automation.agent_module_paths())
import_agent_modules(paths)
bootstrap_agents(...)
```

---

## Out of scope

| Item | Reason |
|---|---|
| Auto-discovery without explicit paths | `agent_module_paths()` is explicit and safer |
| Moving agent tests with agents | Tests live in each package's `tests/` tree |
| `ZePlugin.agents()` returning instances | `_resolve()` handles DI from constructor types |

---

## Success criteria

| Criterion | Check |
|---|---|
| No domain agents under `apps/ze-api/ze_api/agents/` | Directory absent |
| `ze_api/bootstrap.py` absent | Deleted in Phase 76 |
| Plugin agents registered via entry points + `agent_module_paths()` | `make test-api` passes |
