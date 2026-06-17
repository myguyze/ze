from __future__ import annotations

import importlib
import inspect
import sys
import types as _types
import typing
from typing import Any, get_type_hints

from ze_agents.errors import AgentConfigError
from ze_agents.logging import get_logger
from ze_agents.registry import (
    get_registered_agents,
    register_instance,
)
from ze_agents.plugin import ZePlugin

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Legacy static list — kept for tests and no-plugin bootstrap paths.
# Production code derives paths from plugin instances via agent_module_paths().
# ---------------------------------------------------------------------------
_DEFAULT_AGENT_MODULE_PATHS = [
    "ze_personal.contacts.tools",
    "ze_browser.tool",
    "ze_personal.agents.goals.agent",
    "ze_personal.agents.workflow.agent",
    "ze_personal.agents.research.agent",
    "ze_personal.agents.companion.agent",
    "ze_calendar.agents.calendar.agent",
    "ze_calendar.agents.reminders.agent",
    "ze_email.agents.email.tools",
    "ze_email.agents.email.agent",
    "ze_prospecting.agents.tools",
    "ze_prospecting.agents.agent",
]

_dep_map: dict[type, Any] = {}


def discover_plugins(dep_map: dict[type, Any] | None = None) -> list[ZePlugin]:
    """Load and instantiate all Ze plugins declared via entry points.

    Reads ``[project.entry-points."ze.plugins"]`` from every installed package,
    loads each class, topologically sorts by ``cls.depends_on`` (class names),
    and instantiates via ``_resolve()``.

    Returns the ordered list of plugin instances. Raises ``AgentConfigError`` on
    missing deps or dependency cycles.
    """
    from importlib.metadata import entry_points

    effective_deps = dep_map if dep_map is not None else _dep_map
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
                f"Entry point {ep.name!r} points to {cls!r}, "
                f"which is not a ZePlugin subclass."
            )

        entries.append((ep.name, cls))

    if not entries:
        log.warning("no_plugins_discovered")
        return []

    sorted_entries = _topological_sort(entries)

    discovered: list[ZePlugin] = []
    for ep_name, cls in sorted_entries:
        instance = _resolve(cls, effective_deps)
        log.info("plugin_instantiated", name=ep_name, cls=cls.__qualname__)
        discovered.append(instance)

    return discovered


def _topological_sort(
    entries: list[tuple[str, type]],
) -> list[tuple[str, type]]:
    """Sort plugin entries by ``cls.depends_on`` (class names) using Kahn's algorithm.

    Raises ``AgentConfigError`` on unknown deps or cycles.
    """
    name_to_idx: dict[str, int] = {cls.__name__: i for i, (_, cls) in enumerate(entries)}
    n = len(entries)
    adj: list[list[int]] = [[] for _ in range(n)]
    in_degree = [0] * n

    for i, (_, cls) in enumerate(entries):
        for dep_name in getattr(cls, "depends_on", ()):
            j = name_to_idx.get(dep_name)
            if j is None:
                raise AgentConfigError(
                    f"Plugin {cls.__name__!r} declares depends_on={dep_name!r} "
                    f"but no plugin with that class name was discovered."
                )
            adj[j].append(i)
            in_degree[i] += 1

    queue = [i for i in range(n) if in_degree[i] == 0]
    result: list[tuple[str, type]] = []
    while queue:
        node = queue.pop(0)
        result.append(entries[node])
        for j in adj[node]:
            in_degree[j] -= 1
            if in_degree[j] == 0:
                queue.append(j)

    if len(result) != n:
        cycle = [entries[i][1].__name__ for i in range(n) if in_degree[i] > 0]
        raise AgentConfigError(f"Circular plugin dependency detected among: {cycle}")

    return result


def bootstrap_agents(
    *,
    deps: dict[type, Any] | None = None,
    plugins: list[ZePlugin] | None = None,
) -> None:
    """Instantiate and register all enabled agents. Called once at app startup."""
    _dep_map.clear()
    if deps:
        _dep_map.update(deps)

    for module_path in _plugin_agent_module_paths(plugins):
        log.debug("importing_agent_module", path=module_path)
        importlib.import_module(module_path)

    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls)
        register_instance(name, instance)
        log.debug("agent_registered", name=name, cls=cls.__name__)

    validate_registry()
    log.info("bootstrap_complete", agents=list(get_registered_agents()))


def validate_registry() -> None:
    """Cross-check declared tools against the tool registry."""
    from ze_agents.tool import registered_tools

    tool_reg = registered_tools()

    for name, cls in get_registered_agents().items():
        declared_tools: list[str] = getattr(cls, "tools", [])

        for tool_name in declared_tools:
            if tool_name.startswith("openrouter:"):
                continue
            if tool_name == "delegate_to_agent":
                continue
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {name!r} declares unknown tool {tool_name!r}. "
                    f"Ensure the agent's tools module is imported at startup."
                )


def _plugin_agent_module_paths(plugins: list[ZePlugin] | None) -> list[str]:
    """Collect agent module paths from plugin instances.

    When plugins are provided, derives all paths exclusively from them —
    no static fallback. When no plugins are given, falls back to the legacy
    static list so no-plugin bootstrap paths (tests, evals) still work.
    """
    if plugins:
        paths: list[str] = []
        for plugin in plugins:
            plugin_paths = plugin.agent_module_paths()
            log.debug(
                "plugin_agent_modules",
                plugin=type(plugin).__name__,
                paths=plugin_paths,
            )
            paths.extend(plugin_paths)
        return paths
    return list(_DEFAULT_AGENT_MODULE_PATHS)


def reload_agent_modules(plugins: list | None = None) -> None:
    """Force @agent registration after tests replace the ze-core registry."""
    from ze_agents.registry import _instances, _registry
    from ze_agents.tool import clear_tool_registry

    module_paths = (
        _plugin_agent_module_paths(plugins)
        if plugins is not None
        else _DEFAULT_AGENT_MODULE_PATHS
    )

    _registry.clear()
    _instances.clear()
    clear_tool_registry()
    for module_path in module_paths:
        sys.modules.pop(module_path, None)
    for module_path in module_paths:
        importlib.import_module(module_path)


def _resolve_annotation(annotation: Any, dep_map: dict) -> tuple[bool, Any]:
    """Resolve an annotation against dep_map, handling Optional[T] / T | None.

    Returns (found, value). When found=False the caller should check the param
    default and either skip or raise.
    """
    if annotation in dep_map:
        return True, dep_map[annotation]

    # Handle Optional[T] (typing.Union[T, None]) and T | None (3.10+ union).
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    is_optional_union = (
        (origin is typing.Union and type(None) in args)
        or (isinstance(annotation, _types.UnionType) and type(None) in args)
    )
    if is_optional_union:
        inner_types = [a for a in args if a is not type(None)]
        for inner in inner_types:
            if inner in dep_map:
                return True, dep_map[inner]
        # Inner type not registered — treat as missing (caller handles default).
        return False, None

    return False, None


def _hint_namespace(cls: type, dep_map: dict) -> dict[str, Any]:
    module = sys.modules.get(cls.__module__)
    globalns = dict(vars(module)) if module is not None else {}
    for typ in dep_map:
        name = getattr(typ, "__name__", None)
        if name:
            globalns[name] = typ
    return globalns


def _resolve(cls: type, dep_map: dict | None = None) -> object:
    """Instantiate cls by matching __init__ parameter types against dep_map.

    Parameters with defaults are skipped when their type is not registered —
    the default value is used instead. This supports Optional[T] and T | None
    annotations, including GoogleCredentials | None patterns used in plugins.
    """
    effective = dep_map if dep_map is not None else _dep_map
    globalns = _hint_namespace(cls, effective)

    try:
        hints = get_type_hints(cls.__init__, globalns=globalns, localns=globalns)
    except Exception as exc:
        raise AgentConfigError(
            f"Cannot resolve type hints for {cls.__name__}.__init__: {exc}"
        ) from exc

    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "args", "kwargs"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        annotation = hints.get(param_name)
        if annotation is None:
            raise AgentConfigError(
                f"{cls.__name__}.__init__ parameter {param_name!r} has no type annotation"
            )

        found, value = _resolve_annotation(annotation, effective)
        if found:
            kwargs[param_name] = value
        elif param.default is not inspect.Parameter.empty:
            pass  # use the declared default — don't add to kwargs
        else:
            raise AgentConfigError(
                f"No dependency registered for type {annotation!r} "
                f"(required by {cls.__name__}). "
                f"Add it to the dep_map before calling bootstrap_agents()."
            )

    return cls(**kwargs)
