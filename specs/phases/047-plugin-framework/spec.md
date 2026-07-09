# Plugin Framework — Spec

> **Packages:** `ze_core` (plugin ABC), `ze_api` (bootstrapper, container)
> **Phase:** 47
> **Status:** Done (tool namespacing deferred)

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
| Entry point discovery in bootstrapper (auto-instantiate from entry points) | ✅ Done — `discover_plugins()` reads entry points, instantiates via `_resolve()` |
| Plugin-scoped DI via extended `_resolve()` (plugin constructor from `_dep_map`) | ✅ Done — `_resolve()` handles Optional types and default params; all plugin constructors take only dep_map types |
| Schema readiness validation | ✅ Done — startup compares DB Alembic heads against combined ze-core/plugin migration heads (ze-api owns no tables) |
| Tool registry namespacing | 🔲 Deferred — keep fail-fast bare-name registry until a concrete duplicate-name need appears |
| Tests | ✅ Focused startup and migration readiness coverage added |

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
- Replace the static `_DEFAULT_AGENT_MODULE_PATHS` list (removed in Phase 76) with
  discovery via `importlib.metadata.entry_points(group="ze.plugins")` in
  `ze_plugin/bootstrap.py`.
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
core/ze-plugin/
  ze_plugin/
    plugin.py          ← ZePlugin ABC — startup/shutdown hooks
    bootstrap.py       ← plugin discovery, DI, build_integrations()

core/ze-agents/
  ze_agents/
    bootstrap.py       ← bootstrap_agents(), validate_registry()
    tool.py            ← @tool registry (plugin-scoped namespacing deferred)

apps/ze-api/
  ze_api/
    container.py       ← build_container(); calls package bootstraps

plugins/ze-*/
  pyproject.toml       ← [project.entry-points."ze.plugins"]
```

---

## Interface Contract

### `ZePlugin` ABC additions (`ze_plugin/plugin.py`)

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

### Bootstrapper discovery (`ze_plugin/bootstrap.py`)

```python
def discover_plugins() -> list[ZePlugin]:
    """Load and instantiate all registered Ze plugins via entry points."""
    from importlib.metadata import entry_points
    from ze_plugin.plugin import ZePlugin

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

Before building the application container, startup checks the database's Alembic
state against the combined ze-core and plugin migration heads collected
by `ze_api.migrate`:

```python
def assert_schema_ready(database_url: str | None = None) -> None:
    expected_heads = set(ScriptDirectory.from_config(cfg).get_heads())
    current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads != expected_heads:
        raise MigrationReadinessError("Run `make migrate` before starting the server.")
```

Startup aborts hard. A service with unapplied migrations must never serve requests.

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
(`"ze_email.send_email"`) if/when namespacing is implemented. LLM schemas should
continue to use only the short name (`send_email`) in the `name` field passed to
the model — the mapping is resolved internally.

Tools that pre-date namespacing (imported directly without a plugin context) register
under their bare name and emit a deprecation warning.

---

## Startup Sequence

```
1.  Load settings and configure logging.
2.  If `auto_migrate` is enabled, run `ze_api.migrate.upgrade()`.
3.  Run `ze_api.migrate.assert_schema_ready()` — abort if the DB is not at all
    configured Alembic heads.
4.  Build _dep_map (pool, openrouter_client, settings, etc.) — same as today.
5.  discover_plugins()
    a. Load each entry point, instantiate via _resolve(), log.
    b. Collect agent_module_paths() from each plugin.
6.  Import all agent modules (fires @agent and @tool registration).
7.  validate_registry() — cross-check tools and intent_map.
8.  Instantiate agent objects via _resolve(); register_instance() for each.
9.  Build EmbeddingRouter, CapabilityGate, MemoryStore, LangGraph graph.
10. Build ZeContainer.
11. Call plugin.startup(container) for each plugin, in discovery order.
    (FastAPI lifespan yields here — server is now accepting requests.)
12. [shutdown] Call plugin.shutdown() in reverse order, then container.close().
```

Step 11's `startup()` calls are sequential and ordered for deterministic logging and
shutdown symmetry. Startup hooks must not depend on other plugins' startup
side-effects unless a concrete dependency contract is introduced in a future phase.

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

## Resolved Decisions

- **Full plugin auto-instantiation via entry points.** Resolved: shipped. `discover_plugins()`
  reads `ze.plugins` entry points and instantiates plugin classes via `_resolve()` using
  the typed dependency map.
- **Plugin dependency ordering.** Resolved: do not introduce ordering metadata in this
  phase. `startup()` hooks must not depend on another plugin's startup side-effects;
  add an explicit dependency contract only when a concrete case appears.
- **Alembic schema check implementation.** Resolved: use the in-process Alembic API.
  `ze_api.migrate.assert_schema_ready()` reuses the same combined migration config as
  `make migrate` and fails startup before container/plugin initialization when the DB
  is not stamped at every configured head.
- **Tool namespacing rollout.** Resolved: defer namespacing. The current bare-name
  registry already fails fast on duplicate tool names, so this is a future compatibility
  feature for allowing duplicate local tool names across plugins, not a phase blocker.
