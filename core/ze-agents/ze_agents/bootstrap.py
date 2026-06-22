from __future__ import annotations

import importlib
import inspect
import sys
import types as _types
import typing
from typing import Any, get_type_hints

from ze_agents.errors import AgentConfigError
from ze_agents.logging import get_logger
from ze_agents.registry import get_registered_agents, register_instance

log = get_logger(__name__)

_dep_map: dict[type, Any] = {}


def bootstrap_agents(
    *,
    deps: dict[type, Any] | None = None,
    plugins: list[Any],
) -> None:
    if not plugins:
        raise AgentConfigError("bootstrap_agents() requires a non-empty plugins list")

    _dep_map.clear()
    if deps:
        _dep_map.update(deps)

    for module_path in _plugin_agent_module_paths(plugins):
        log.debug("importing_agent_module", path=module_path)
        importlib.import_module(module_path)

    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls, _dep_map)
        register_instance(name, instance)
        log.debug("agent_registered", name=name, cls=cls.__name__)

    validate_registry()
    log.info("bootstrap_complete", agents=list(get_registered_agents()))


def validate_registry() -> None:
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


def _plugin_agent_module_paths(plugins: list[Any]) -> list[str]:
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


def reload_agent_modules(module_paths: list[str]) -> None:
    if not module_paths:
        raise AgentConfigError("reload_agent_modules() requires a non-empty module_paths list")

    from ze_agents.registry import _instances, _registry
    from ze_agents.tool import clear_tool_registry

    _registry.clear()
    _instances.clear()
    clear_tool_registry()
    for module_path in module_paths:
        sys.modules.pop(module_path, None)
    for module_path in module_paths:
        importlib.import_module(module_path)


def _resolve_annotation(annotation: Any, dep_map: dict) -> tuple[bool, Any]:
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


def _resolve(cls: type, dep_map: dict | None = None) -> object:
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
            pass
        else:
            raise AgentConfigError(
                f"No dependency registered for type {annotation!r} "
                f"(required by {cls.__name__}). "
                f"Add it to the dep_map before calling bootstrap_agents()."
            )

    return cls(**kwargs)
