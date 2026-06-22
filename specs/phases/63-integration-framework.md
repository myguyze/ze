# Integration Framework — Spec

> **Packages:** `ze_plugin` (Protocol + ZePlugin hook), `ze_plugin/bootstrap.py` (wiring), integration packages (`integrations/`)
> **Phase:** 63
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ZeIntegration` Protocol in `ze_agents` | ✅ Done |
| `ZePlugin.integration_types()` classmethod | ✅ Done |
| Bootstrapper split: `_load_plugin_classes` + `instantiate_plugins` | ✅ Done |
| `build_integrations()` helper | ✅ Done |
| Remove manual `GoogleCredentials` wiring from `build_container` | ✅ Done |
| `ze-google` declared by consuming plugins | ✅ Done |
| `integrations/README.md` updated | ✅ Done |
| Tests | ✅ Done (262 passing) |

---

## Purpose

Every new external integration added to Ze requires a manual touch to `build_container`:
instantiate credentials, add to `plugin_deps`, and ensure the type is registered before
plugins are resolved. This makes `container.py` a merge-conflict magnet and produces no
compile-time guarantee that an integration a plugin needs will actually be built.

This phase introduces a standard contract for integration packages and a `ZePlugin` hook
that lets plugins declare what integrations they need. `build_container` then auto-builds
all required integrations without knowing about any specific one — adding a new integration
requires zero changes to `container.py`.

---

## Responsibilities

- Define `ZeIntegration` as a structural `Protocol` in `ze_agents` that integration packages
  satisfy without importing from Ze.
- Add `ZePlugin.integration_types()` classmethod so plugins declare their integration dependencies
  before plugin instantiation occurs.
- Split `discover_plugins()` in `bootstrap.py` into two steps: class loading (before integrations
  are built) and instantiation (after integrations are in `plugin_deps`).
- Add `build_integrations()` helper that deduplicates types, calls `from_settings`, and returns
  a `dict[type, Any]` ready to merge into `plugin_deps`.
- Remove the hardcoded `GoogleCredentials.from_settings(settings)` block from `build_container`.
- Update `integrations/README.md` with the `ZeIntegration` contract every new integration package
  must satisfy.

---

## Out of Scope

- Async integration initialization (e.g. OAuth2 token exchange at startup). Plugins that need
  async init continue to use `plugin.startup(container)`.
- Changing `ze_api/settings.py` attribute naming conventions for integration env vars.
- Moving env var reading out of `from_settings` (e.g. reading `os.environ` directly instead
  of a `Settings` object).
- Integration health checks or credential validation at startup — that is a plugin's
  responsibility in `startup()`.
- Multi-user or per-request credential scoping — Ze is single-user; credentials are singletons.
- Version compatibility checks between an integration package and Ze core.

---

## Module Location

```
core/ze-agents/
  ze_agents/
    integration.py       ← NEW: ZeIntegration Protocol
    plugin.py            ← add integration_types() classmethod

apps/ze-api/
  ze_api/
    container.py         ← calls build_integrations() from ze_plugin.bootstrap

integrations/ze-google/
  ze_google/
    auth.py              ← no code change; satisfies ZeIntegration structurally

plugins/ze-email/
  ze_email/plugin.py     ← add integration_types() → [GoogleCredentials]

plugins/ze-calendar/
  ze_calendar/plugin.py  ← add integration_types() → [GoogleCredentials]
```

---

## Interface Contract

### `ZeIntegration` Protocol (`ze_agents/integration.py`)

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class ZeIntegration(Protocol):
    """Structural protocol that every integration credentials class must satisfy.

    Integration packages (under integrations/) never import this — they satisfy
    it structurally. The protocol is used only by bootstrap.py for validation.
    """

    @classmethod
    def from_settings(cls, settings: Any) -> "ZeIntegration | None":
        """Build from app settings. Return None if the integration is not configured
        (e.g. required env vars absent). Returning None is not an error — it means
        the integration is optional and consuming plugins will receive None via DI.
        """
        ...
```

`@runtime_checkable` allows `isinstance(GoogleCredentials, ZeIntegration)` checks in
the bootstrapper to validate integration types at startup without import coupling.

Integration packages **never import** `ZeIntegration`. They satisfy it by implementing
the `from_settings` classmethod with the correct signature. This preserves the
"integrations have no Ze deps" rule.

---

### `ZePlugin.integration_types()` (`ze_agents/plugin.py`)

```python
class ZePlugin(ABC):
    # ... existing hooks ...

    @classmethod
    def integration_types(cls) -> list[type]:
        """Return integration credential types this plugin needs.

        Each type must satisfy the ZeIntegration protocol (implement
        from_settings(settings) -> T | None). Must be a classmethod so the
        bootstrapper can collect types before plugin instantiation.

        The bootstrapper deduplicates across plugins, calls from_settings once
        per unique type, and adds results to plugin_deps. Plugin constructors
        then receive credentials via normal DI (Optional[T] | None).
        """
        return []
```

**Why classmethod:** `discover_plugin_classes()` runs before `_resolve()` so integration
deps are available when plugin `__init__` parameters are resolved. An instance method
would require a two-phase plugin construction that is more complex than a classmethod.

---

### Bootstrapper split (`ze_plugin/bootstrap.py`)

The current `discover_plugins(dep_map)` does class loading + topological sort +
instantiation in one pass. We split it:

```python
def _load_plugin_classes() -> list[tuple[str, type[ZePlugin]]]:
    """Load and topologically sort plugin classes from entry points.

    Does NOT instantiate. Safe to call before plugin_deps is fully populated.
    Returns list of (ep_name, cls) pairs in dependency order.
    """
    from importlib.metadata import entry_points

    entries: list[tuple[str, type]] = []
    for ep in entry_points(group="ze.plugins"):
        log.info("plugin_discovered", name=ep.name, value=ep.value)
        try:
            cls = ep.load()
        except Exception as exc:
            log.error("plugin_load_failed", name=ep.name, error=str(exc))
            raise AgentConfigError(
                f"Failed to load plugin entry point {ep.name!r}: {exc}"
            ) from exc

        if not (isinstance(cls, type) and issubclass(cls, ZePlugin)):
            raise AgentConfigError(
                f"Entry point {ep.name!r} → {cls!r} is not a ZePlugin subclass."
            )
        entries.append((ep.name, cls))

    if not entries:
        log.warning("no_plugins_discovered")
        return []

    return _topological_sort(entries)


def _instantiate_plugins(
    sorted_entries: list[tuple[str, type[ZePlugin]]],
    dep_map: dict[type, Any],
) -> list[ZePlugin]:
    """Instantiate topologically sorted plugin classes via _resolve()."""
    discovered: list[ZePlugin] = []
    for ep_name, cls in sorted_entries:
        instance = _resolve(cls, dep_map)
        log.info("plugin_instantiated", name=ep_name, cls=cls.__qualname__)
        discovered.append(instance)
    return discovered


def discover_plugins(dep_map: dict[type, Any] | None = None) -> list[ZePlugin]:
    """Load, sort, and instantiate all Ze plugins. Backwards-compatible entry point."""
    effective = dep_map if dep_map is not None else _dep_map
    sorted_entries = _load_plugin_classes()
    return _instantiate_plugins(sorted_entries, effective)
```

---

### `build_integrations()` helper (`ze_plugin/bootstrap.py`)

```python
def build_integrations(
    plugin_classes: list[tuple[str, type[ZePlugin]]],
    settings: Any,
) -> dict[type, Any]:
    """Collect and build all integration deps declared by plugin classes.

    Deduplicates types across plugins, validates each satisfies ZeIntegration,
    calls from_settings once per unique type, and returns a dep_map fragment.
    Returning None from from_settings is allowed — plugins receive None via DI.
    """
    from ze_agents.integration import ZeIntegration

    seen: dict[type, Any] = {}
    for _name, cls in plugin_classes:
        for itype in cls.integration_types():
            if itype in seen:
                continue
            if not (isinstance(itype, type) and isinstance(itype, ZeIntegration)):
                raise AgentConfigError(
                    f"Integration type {itype!r} declared by {cls.__name__} does not "
                    f"satisfy the ZeIntegration protocol (missing from_settings classmethod)."
                )
            instance = itype.from_settings(settings)
            seen[itype] = instance
            if instance is None:
                log.warning(
                    "integration_not_configured",
                    type=itype.__name__,
                    hint="check .env for missing credentials",
                )
            else:
                log.info("integration_built", type=itype.__name__)
    return seen
```

---

### Updated `build_container` call site (`ze_api/container.py`)

**Remove:**
```python
google_credentials = GoogleCredentials.from_settings(settings)
```
and its entry in `plugin_deps`:
```python
GoogleCredentials: google_credentials,
```

**Replace with:**
```python
# After building base plugin_deps and before discover_plugins:
plugin_classes = _load_plugin_classes()
integration_deps = build_integrations(plugin_classes, settings)
plugin_deps.update(integration_deps)
plugins = _instantiate_plugins(plugin_classes, plugin_deps)
```

The `discover_plugins(plugin_deps)` call is replaced by the explicit three-step sequence
so `build_integrations` can run between class loading and instantiation.

---

### Plugin declaration (`ze_email/plugin.py`, `ze_calendar/plugin.py`)

```python
# ze_email/plugin.py
class EmailPlugin(ZePlugin):
    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]

# ze_calendar/plugin.py
class CalendarPlugin(ZePlugin):
    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]
```

The import inside the method body keeps the plugin's module-level imports clean and
avoids circular import risk. Both plugins declare `GoogleCredentials` — `build_integrations`
deduplicates by type so `from_settings` is called exactly once.

---

## Convention for New Integrations

Every package under `integrations/` must expose at least one credentials class with:

```python
@classmethod
def from_settings(cls, settings) -> "MyCredentials | None":
    """Read named attributes from settings (duck-typed — do not import Settings).
    Return None when any required env var is absent.
    """
    if not all([settings.my_service_api_key]):
        return None
    return cls(api_key=settings.my_service_api_key)
```

Rules:
1. **No Ze imports** — integration packages have zero Ze dependencies.
2. **Duck-typed settings** — read named attributes from a settings object passed at
   startup; never import `ZeApiSettings` from ze-api. Integration-owned env vars live
   in the integration package's own settings module (e.g. `ze_google.settings.GoogleSettings`).
3. **Return `None` when unconfigured** — never raise from `from_settings`. Plugins
   that require the integration enforce that constraint in `startup()`.
4. **Synchronous** — `from_settings` is called synchronously at startup. Async init
   (token exchange, connection warmup) goes in `plugin.startup(container)`.
5. **Stateless across requests** — credentials objects are singletons; they must be
   safe to share across concurrent async tasks.

---

## Env Var Naming Convention

Integration env vars follow the pattern `SERVICE_CREDENTIAL_NAME`:

| Integration | Env Var | Settings Attr |
|-------------|---------|---------------|
| Google OAuth2 | `GOOGLE_CLIENT_ID` | `GoogleSettings.google_client_id` |
| Google OAuth2 | `GOOGLE_CLIENT_SECRET` | `GoogleSettings.google_client_secret` |
| Google OAuth2 | `GOOGLE_REFRESH_TOKEN` | `GoogleSettings.google_refresh_token` |
| Future: GitHub | `GITHUB_TOKEN` | integration package settings attr |
| Future: Stripe | `STRIPE_SECRET_KEY` | integration package settings attr |

Integration env vars are declared in the owning integration package's settings class,
not in `ZeApiSettings`. ze-api passes a merged settings object (or integration-specific
settings) into `build_integrations()` at container startup.

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Integration type missing `from_settings` | `AgentConfigError` at startup — clear message naming the plugin and type |
| `from_settings` returns `None` | Logged at WARNING with a hint to check `.env`; `None` is stored in `plugin_deps`; plugin DI resolves `Optional[T]` → `None` |
| Plugin `__init__` requires `T` (non-optional) but `from_settings` → `None` | `AgentConfigError` from `_resolve()` — "No dependency registered for type T" |
| Same integration type declared by multiple plugins | `build_integrations` deduplicates by type; `from_settings` called once |
| Integration type not registered in any plugin's `integration_types()` | It will never be built; if `plugin_deps` still contains it explicitly that is a bug |
| `from_settings` raises | Exception propagates — startup aborts; fix the integration package |

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_agents.plugin` | `ZePlugin` ABC — add `integration_types()` classmethod |
| `ze_agents.integration` | NEW: `ZeIntegration` Protocol |
| `ze_agents.errors` | `AgentConfigError` |
| `ze_api.bootstrap` | `build_integrations`, `_load_plugin_classes`, `_instantiate_plugins` |
| `ze_api.container` | Remove manual `GoogleCredentials` wiring |

---

## Implementation Notes

- `@runtime_checkable` on `ZeIntegration` allows `isinstance(itype, ZeIntegration)` at
  startup without integration packages needing to import from `ze_agents`. Python's
  structural check only verifies the classmethod name exists, not its signature — the
  protocol is a guardrail, not a full type check.
- The import of `GoogleCredentials` inside `integration_types()` body (rather than at
  module top) mirrors the TYPE_CHECKING pattern already in `ze_email/plugin.py` and
  avoids circular imports during module load order.
- `build_integrations` must run after `_load_plugin_classes` but before `_instantiate_plugins`.
  The call order in `build_container` is the only place that enforces this — do not merge
  these steps back together.
- Tests that use `discover_plugins(dep_map)` directly are unaffected — the function
  signature and behaviour are unchanged (it still does class loading + instantiation).
  Tests that need to inject a fake integration should add the type to the dep_map passed
  to `discover_plugins` as before.

---

## Resolved Questions

- [x] **WARNING vs INFO for unconfigured integrations.** Resolved: WARNING. Ze is
  single-user — `from_settings` returning `None` almost always means a missing env var.
  Silent INFO is too quiet for something that disables an entire agent family; WARNING
  surfaces it immediately at startup.

- [x] **`required_integrations()` classmethod.** Resolved: do not add it. The existing
  `startup()` hook is the correct place for integration invariants. A plugin that cannot
  function without a credential raises `PluginConfigError` in `startup()` when it finds
  `None`:
  ```python
  async def startup(self, container):
      if self._github_credentials is None:
          raise PluginConfigError(
              "GitHubPlugin requires GITHUB_TOKEN — set it in .env."
          )
  ```
  Adding `required_integrations()` would create two mechanisms to declare the same
  constraint. Keep the framework minimal; `startup()` already handles enforcement.
