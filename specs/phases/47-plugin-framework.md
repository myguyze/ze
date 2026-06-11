# Plugin Framework — Spec

> **Packages:** `ze_core` (plugin ABC), `ze_api` (bootstrapper, container)
> **Phase:** 47
> **Status:** In Progress (lifecycle hooks + entry points shipped; full DI deferred)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ZePlugin` lifecycle hooks (`startup` / `shutdown`) | ✅ Done |
| Entry point declaration in all plugin `pyproject.toml`s | ✅ Done |
| `_plugin_agent_module_paths()` derives from plugin instances (no static fallback when plugins provided) | ✅ Done |
| Bootstrapper startup/shutdown wiring in `container.py` | ✅ Done |
| Bootstrapper discovery logging | ✅ Done |
| Missing module paths moved into plugin `agent_module_paths()` | ✅ Done |
| Entry point discovery in bootstrapper (auto-instantiate from entry points) | 🔲 Deferred — requires full plugin DI via `_resolve()` |
| Plugin-scoped DI via extended `_resolve()` (plugin constructor from `_dep_map`) | 🔲 Deferred — requires moving service construction into plugin `__init__` |
| Schema readiness validation | 🔲 Deferred — see Open Questions |
| Tool registry namespacing | 🔲 Deferred — breaking change, see Open Questions |
| Tests | ✅ All 165 existing tests passing |

---

## Purpose

Adding a new Ze plugin currently requires touching four separate locations: subclass
`ZePlugin`, implement `agent_module_paths()`, call `register_instance()` in
`ze_api/container.py`, and import tool modules at startup. Every new package requires
a human to modify the central `container.py`, making it a merge-conflict magnet and
a source of silent startup failures when a step is missed.

This phase introduces entry point-based plugin discovery so that adding a plugin
requires exactly one line in the package's `pyproject.toml` and zero changes to
`container.py`. It also fixes three structural gaps the current design carries:
plugins have no async lifecycle hooks (breaking async initialisation), `container.py`
wires plugin services manually (negating the value of the existing `_resolve()` DI),
and the `@tool` registry has no namespacing (enabling silent collisions).

---

## Responsibilities

- Define `async startup(container)` and `async shutdown()` on `ZePlugin` ABC as
  no-op defaults, called by the bootstrapper at FastAPI lifespan boundaries.
- Replace the static `_DEFAULT_AGENT_MODULE_PATHS` list in `bootstrap.py` with
  discovery via `importlib.metadata.entry_points(group="ze.plugins")`.
- Extend `_resolve()` to instantiate plugin classes (not just agents) from the
  shared `_dep_map`, eliminating manual per-service wiring in `container.py`.
- Validate schema readiness for each plugin that declares `migrations_path()` before
  calling `startup()`.
- Namespace the `@tool` global registry by plugin (`{plugin_name}.{tool_name}`
  internally) to prevent silent clobbering when two plugins register tools with
  the same name.
- Log every plugin discovered, every plugin skipped (with reason), and every
  dependency resolved at INFO level so failures are traceable without reading source.

---

## Out of Scope

- Removing explicit `register_instance()` from tests — it remains a valid escape hatch.
- Hot-reloading plugins at runtime without server restart.
- Plugin versioning or compatibility checks between plugin and ze-core versions.
- Changing the `ZePlugin` graph-level hooks (`state_extensions`, `pre_route_node`,
  `graph_nodes`, `graph_edges`, `configurable_services`) — those are out of scope.
- The public LLM tool description format — tool names as seen by the LLM are
  unchanged; namespacing is internal only.

---

## Module Location

```
core/ze-core/
  ze_core/
    plugin.py          ← ZePlugin ABC — add startup/shutdown hooks
    orchestration/
      tool.py          ← @tool registry — add plugin-scoped namespacing

apps/ze-api/
  ze_api/
    bootstrap.py       ← replace _DEFAULT_AGENT_MODULE_PATHS with entry_points scan
    container.py       ← remove per-plugin manual wiring; call plugin.startup()

plugins/ze-*/
  pyproject.toml       ← add [project.entry-points."ze.plugins"] stanza
```

---

## Interface Contract

### `ZePlugin` ABC additions (`ze_core/plugin.py`)

```python
class ZePlugin(ABC):
    # Existing hooks unchanged.

    async def startup(self, container: "ZeContainer") -> None:
        """Called once during FastAPI lifespan startup, after DI is resolved.

        Override to run async initialisation: open DB pools, start schedulers,
        validate credentials, etc. Default is a no-op.
        """

    async def shutdown(self) -> None:
        """Called once during FastAPI lifespan shutdown, in reverse startup order.

        Override to release async resources. Default is a no-op.
        """
```

`startup()` receives the fully-built `ZeContainer` so plugins can read shared
singletons (pool, openrouter client, scheduler) without requiring them as
constructor parameters. `shutdown()` receives nothing — plugins track their own
resources.

### Entry point declaration (each plugin `pyproject.toml`)

```toml
[project.entry-points."ze.plugins"]
ze_personal     = "ze_personal.plugin:PersonalPlugin"
ze_calendar     = "ze_calendar.plugin:CalendarPlugin"
ze_email        = "ze_email.plugin:EmailPlugin"
ze_prospecting  = "ze_prospecting.plugin:ProspectingPlugin"
ze_news         = "ze_news.plugin:NewsPlugin"
```

Key is the plugin's canonical name (used for tool namespacing and log messages).
Value is `module:class` pointing to the `ZePlugin` subclass.

### Bootstrapper discovery (`ze_api/bootstrap.py`)

```python
def discover_plugins() -> list[ZePlugin]:
    """Load and instantiate all registered Ze plugins via entry points."""
    from importlib.metadata import entry_points
    from ze_core.plugin import ZePlugin

    discovered: list[ZePlugin] = []
    for ep in entry_points(group="ze.plugins"):
        log.info("plugin_discovered", name=ep.name, value=ep.value)
        try:
            cls = ep.load()
        except Exception as exc:
            log.error("plugin_load_failed", name=ep.name, error=str(exc))
            raise
        if not issubclass(cls, ZePlugin):
            raise PluginConfigError(
                f"Entry point {ep.name!r} points to {cls!r}, which is not a ZePlugin subclass"
            )
        instance = _resolve(cls)
        log.info("plugin_instantiated", name=ep.name, cls=cls.__qualname__)
        discovered.append(instance)

    if not discovered:
        log.warning("no_plugins_discovered")
    return discovered
```

`_resolve()` is extended to accept any class (not just `BaseAgent`) and resolves
its `__init__` parameters against `_dep_map`. Plugin constructors must be
type-annotated. If a required type is absent from `_dep_map`, startup aborts with
`PluginConfigError`.

### Schema readiness validation

Before calling `startup()` on any plugin, the bootstrapper checks Alembic migration
state for plugins that declare `migrations_path()`:

```python
async def _check_schema_readiness(plugins: list[ZePlugin], settings: Settings) -> None:
    for plugin in plugins:
        path = plugin.migrations_path()
        if path is None:
            continue
        current = _alembic_current_heads(settings.database_url_sync, path)
        expected = _alembic_head_revision(path)
        if current != expected:
            raise PluginConfigError(
                f"Plugin {type(plugin).__name__!r} schema is not up to date. "
                f"Run `make migrate` before starting the server. "
                f"Expected {expected!r}, got {current!r}."
            )
```

Startup aborts hard. A plugin with unapplied migrations must never serve requests.

### Tool namespacing (`ze_core/orchestration/tool.py`)

The `@tool` decorator registers tools under a namespaced key:

```python
_tool_registry: dict[str, ToolSpec] = {}  # key: "{plugin_name}.{tool_name}" or "{tool_name}"

def tool(*, access: ToolAccess | str, description: str, plugin: str = "") -> Callable:
    def decorator(fn: Callable) -> Callable:
        name = f"{plugin}.{fn.__name__}" if plugin else fn.__name__
        if name in _tool_registry:
            raise ToolConfigError(f"Duplicate tool registration: {name!r}")
        _tool_registry[name] = ToolSpec(name=name, fn=fn, access=access, description=description)
        return fn
    return decorator
```

The `plugin` parameter is set automatically when tools are imported via a plugin's
`agent_module_paths()` — the bootstrapper sets a context variable before importing
each plugin's tool modules. Agents declare tools by full namespaced key
(`"ze_email.send_email"`). LLM schemas use only the short name (`send_email`) in
the `name` field passed to the model — the mapping is resolved internally.

Tools that pre-date namespacing (imported directly without a plugin context) register
under their bare name and emit a deprecation warning.

---

## Startup Sequence

```
1.  Build _dep_map (pool, openrouter_client, settings, etc.) — same as today.
2.  discover_plugins()
    a. Load each entry point, instantiate via _resolve(), log.
    b. Collect agent_module_paths() from each plugin.
3.  Import all agent modules (fires @agent and @tool registration).
4.  validate_registry() — cross-check tools and intent_map.
5.  _check_schema_readiness() — abort if any plugin has unapplied migrations.
6.  Instantiate agent objects via _resolve(); register_instance() for each.
7.  Build EmbeddingRouter, CapabilityGate, MemoryStore, LangGraph graph.
8.  Build ZeContainer.
9.  Call plugin.startup(container) for each plugin, in discovery order.
    (FastAPI lifespan yields here — server is now accepting requests.)
10. [shutdown] Call plugin.shutdown() in reverse order, then container.close().
```

Steps 9's `startup()` calls are sequential and ordered — a plugin that depends on
another's side-effects (e.g. a scheduler started in step 9a) can rely on earlier
plugins having completed startup. If ordering across plugins matters, it is
determined by the order of entry points (alphabetical within a package by default;
overridable via `depends_on` on the plugin class — see Open Questions).

---

## Migration Path for Existing Plugins

Six plugins are currently wired manually. The transition is backwards-compatible:

1. Add `[project.entry-points."ze.plugins"]` to each plugin's `pyproject.toml`.
2. Move per-plugin service construction out of `container.py` into
   `ZePlugin.__init__` (receiving deps via `_resolve()`).
3. Move async init (schedulers, credential refresh) into `plugin.startup()`.
4. Keep the existing explicit imports in `container.py` as deprecated fallbacks,
   removed once all plugins are verified on entry points.

Existing plugins in order of migration:

| Plugin | Services to move into plugin | Async init to move to startup() |
|--------|------------------------------|---------------------------------|
| `ze_personal` | PersonStore, GoalStore, GoalPlanner, GoalExecutor, WorkflowStore, WorkflowPlanner, WorkflowScheduler, ContactsConsolidator, PersonaStore, GoalSuggestionStore | WorkflowScheduler.start() |
| `ze_calendar` | ReminderStore, CalendarReminderStore, CalendarReminderService | CalendarReminderJob scheduling |
| `ze_email` | (no stores; credentials via GoogleCredentials in dep_map) | — |
| `ze_prospecting` | ProspectCampaignStore, ProspectingSettings | — |
| `ze_news` | NewsStore | — |
| `ze_memory` (ze-core adjacent) | MemoryConsolidator | — |

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| No plugins discovered | Warning logged; startup continues (allows bare ze-core apps) |
| Entry point points to non-`ZePlugin` class | `PluginConfigError` — abort startup |
| Plugin `__init__` requires type not in `_dep_map` | `PluginConfigError` — abort startup |
| Plugin `migrations_path()` schema not up to date | `PluginConfigError` — abort startup |
| Two plugins register same-named tool with no namespace | `ToolConfigError` — abort startup |
| Plugin `startup()` raises | Exception propagates — FastAPI lifespan fails, server does not start |
| Plugin `shutdown()` raises | Exception caught, logged as WARNING; shutdown continues for remaining plugins |

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `importlib.metadata.entry_points` | Plugin discovery (stdlib ≥ 3.9) |
| `alembic` | Schema readiness check (CLI runner in subprocess or direct API) |
| `ze_core.plugin` | `ZePlugin` ABC |
| `ze_core.orchestration.tool` | Tool registry namespacing |
| `ze_core.errors` | `PluginConfigError`, `ToolConfigError` |
| `ze_api.logging` | Structured startup logging |

---

## Implementation Notes

- `entry_points(group="ze.plugins")` returns all installed packages declaring this
  group, in installation order. In development (editable installs via `pip install -e
  .`), all plugins in the monorepo are always discoverable — no extra steps needed.
- The `startup(container)` signature passes `ZeContainer` rather than individual
  services to avoid coupling the plugin ABC to application-level types. Plugins that
  need specific services should receive them via their `__init__` (DI-resolved) rather
  than extracting them from the container in `startup()`.
- Do not use `pkgutil.walk_packages` for discovery — it scans the full installed tree
  and is slow. Entry points are an explicit declaration, not a heuristic scan.
- The `@tool(plugin=...)` parameter should be set by the bootstrapper via a
  `contextvars.ContextVar`, not by the plugin author manually. The import step in the
  bootstrapper sets the context variable before importing each plugin's modules, then
  resets it after. This keeps the `@tool` call site clean.

---

## Open Questions

- [ ] **Full plugin auto-instantiation via entry points.** Currently container.py still
  constructs plugin instances manually. To eliminate this, each plugin's `__init__`
  must take only "primitive" deps (pool, openrouter_client, settings) and construct
  its own stores/services internally. This is a large refactor of every plugin class —
  deferred to a follow-up.
- [ ] **Plugin dependency ordering.** If `PluginB.startup()` depends on a side-effect
  from `PluginA.startup()`, declaration order may not be correct. Document that
  `startup()` must not depend on other plugins' `startup()` side-effects; add
  `depends_on` only if a concrete case arises.
- [ ] **Alembic schema check implementation.** Running Alembic in-process vs. subprocess.
  In-process is cleaner but couples ze-api to alembic internals. Deferred pending
  a concrete plugin that needs it.
- [ ] **Tool namespacing rollout.** Agents currently declare tools by bare name
  (`"send_email"`). Switching to namespaced keys (`"ze_email.send_email"`) is a
  breaking change to every agent's `tools` class attribute. Deferred — prefer one
  grep-and-replace commit when ready.
