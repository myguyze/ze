# ze-plugin — Plugin Extension Framework

> **Package:** `core/ze-plugin` — `ze_plugin/`
> **Status:** Done
> **Implemented in:** [Phase 47](../phases/47-plugin-framework.md), [Phase 64](../phases/64-plugin-package-extraction.md)

---

## Purpose

Defines `ZePlugin` — the ABC every domain package implements to integrate with Ze.
The engine discovers plugins via Python entry points, orders them topologically, and
calls their lifecycle hooks. This package has no domain knowledge; it is the contract
between the engine and domain code.

---

## Responsibilities

- `ZePlugin` ABC — lifecycle hooks: `startup(container)`, `shutdown()`, `agent_module_paths()`, `memory_policies()`, `checkpoint_serde_modules()`, `migrations_path()`, `signal_sources()`, `ui_manifest()`
- `ZeIntegration` Protocol — lightweight integration contract (subset of `ZePlugin` for non-plugin packages)
- `SignalSource` Protocol — plugins that emit signals implement this
- Plugin registry — `get_plugin_registry()` returns registered instances; populated at startup via entry points
- `DataDomain` — data portability hook (moved to `ze-data`)

---

## Out of Scope

- Plugin discovery and ordering — `ze-core` container
- Agent execution — `ze-agents`
- Public plugin API surface — `ze-sdk` (plugins never import `ze_plugin` directly)

---

## Module Location

```
core/ze-plugin/ze_plugin/
  plugin.py        ← ZePlugin ABC
  integration.py   ← ZeIntegration Protocol
  registry.py      ← plugin registry
  signals.py       ← SignalSource Protocol
  channels/        ← channel registration helpers
  ui.py            ← UI manifest hook types
  webhook.py       ← webhook registration hook types
  api_auth.py      ← API auth hook
```

---

## Interface Contract

```python
class ZePlugin(ABC):
    # Declare agent modules to import at startup (fires @agent / @tool registration)
    def agent_module_paths(self) -> list[str]: return []

    # Called after the DI container is wired
    async def startup(self, container: BaseContainer) -> None: pass
    async def shutdown(self) -> None: pass

    # Memory write policies for agents this plugin owns
    def memory_policies(self) -> dict[str, MemoryPolicy]: return {}

    # Pydantic serialiser modules for LangGraph checkpoint types
    def checkpoint_serde_modules(self) -> list[str]: return []

    # Path to this package's Alembic migrations directory
    def migrations_path(self) -> str | None: return None

    # Signal sources this plugin contributes to the correlation engine
    def signal_sources(self) -> list[SignalSource]: return []

    # Server-driven UI manifest entries
    def ui_manifest(self) -> list[ManifestEntry]: return []
```

---

## Entry point convention

```toml
# <package>/pyproject.toml
[project.entry-points."ze.plugins"]
ze_myplugin = "ze_myplugin.plugin:MyPlugin"
```

The engine discovers all `ze.plugins` entry points at startup, instantiates them,
orders by `plugin_deps`, and calls `startup` in dependency order.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `BaseContainer`, `Settings`, shared types |

---

## Implementation Notes

Plugin authors never import from `ze_plugin` directly. They import from `ze_sdk.*`,
which re-exports everything they need. `ze_plugin` is engine-internal and `ze-sdk` is
the stable public surface.
