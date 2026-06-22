from __future__ import annotations

import importlib
import inspect
import sys
import types as _types
import typing
from typing import Any, get_type_hints

from ze_agents.errors import AgentConfigError
from ze_agents.logging import get_logger
from ze_plugin.integration import ZeIntegration
from ze_plugin.plugin import ZePlugin

log = get_logger(__name__)


def load_plugin_classes() -> list[tuple[str, type[ZePlugin]]]:
    """Load and topologically sort plugin classes from entry points."""
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
                f"Entry point {ep.name!r} points to {cls!r}, "
                f"which is not a ZePlugin subclass."
            )
        entries.append((ep.name, cls))

    if not entries:
        log.warning("no_plugins_discovered")
        return []

    return topological_sort(entries)


def instantiate_plugins(
    sorted_entries: list[tuple[str, type[ZePlugin]]],
    dep_map: dict[type, Any],
) -> list[ZePlugin]:
    discovered: list[ZePlugin] = []
    for ep_name, cls in sorted_entries:
        instance = resolve(cls, dep_map)
        log.info("plugin_instantiated", name=ep_name, cls=cls.__qualname__)
        discovered.append(instance)
    return discovered


def build_integrations(
    plugin_classes: list[tuple[str, type[ZePlugin]]],
    settings: Any,
) -> dict[type, Any]:
    seen: dict[type, Any] = {}
    for _name, cls in plugin_classes:
        for itype in cls.integration_types():
            if itype in seen:
                continue
            if not (isinstance(itype, type) and isinstance(itype, ZeIntegration)):
                raise AgentConfigError(
                    f"Integration type {itype!r} declared by {cls.__name__} does not "
                    f"satisfy ZeIntegration (missing from_settings classmethod)."
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


def discover_and_instantiate_plugins(
    dep_map: dict[type, Any],
    settings: Any,
) -> list[ZePlugin]:
    plugin_classes = load_plugin_classes()
    dep_map.update(build_integrations(plugin_classes, settings))
    return instantiate_plugins(plugin_classes, dep_map)


def topological_sort(
    entries: list[tuple[str, type]],
) -> list[tuple[str, type]]:
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


def resolve_annotation(annotation: Any, dep_map: dict) -> tuple[bool, Any]:
    if annotation in dep_map:
        return True, dep_map[annotation]

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


def resolve(cls: type, dep_map: dict | None = None) -> object:
    effective = dep_map if dep_map is not None else {}
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

        found, value = resolve_annotation(annotation, effective)
        if found:
            kwargs[param_name] = value
        elif param.default is not inspect.Parameter.empty:
            pass
        else:
            raise AgentConfigError(
                f"No dependency registered for type {annotation!r} "
                f"(required by {cls.__name__}). "
                f"Add it to the dep_map before instantiating plugins."
            )

    return cls(**kwargs)


def import_plugin_modules_for_migrations() -> None:
    """Import all plugin entry points so migration paths can be collected."""
    for ep_name, cls in load_plugin_classes():
        module = sys.modules.get(cls.__module__)
        if module is None:
            importlib.import_module(cls.__module__)
        log.debug("plugin_module_loaded_for_migrations", name=ep_name, module=cls.__module__)
