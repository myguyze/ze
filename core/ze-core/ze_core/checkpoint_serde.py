"""LangGraph checkpoint serde — builds allowlists from core modules + plugin hooks."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from enum import Enum
from inspect import isclass
from typing import TYPE_CHECKING, Any

from ze_logging import get_logger

if TYPE_CHECKING:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

log = get_logger(__name__)

# Core domain modules scanned on every build. Plugins extend via checkpoint_serde_modules().
CORE_CHECKPOINT_MODULES: tuple[str, ...] = (
    "ze_core.routing.types",
    "ze_agents.types",
    "ze_memory.types",
)

# Driver/stdlib types that appear in checkpoint payloads but live outside core modules.
_EXTRA_CHECKPOINT_TYPES: tuple[tuple[str, str], ...] = (
    ("asyncpg.pgproto.pgproto", "UUID"),
)


def collect_types_from_module(module_name: str) -> set[tuple[str, str]]:
    """Return (module, class_name) pairs for dataclasses and enums defined in a module."""
    mod = importlib.import_module(module_name)
    found: set[tuple[str, str]] = set()
    for _, obj in inspect.getmembers(mod):
        if not isclass(obj):
            continue
        if obj.__module__ != mod.__name__:
            continue
        if dataclasses.is_dataclass(obj):
            found.add((obj.__module__, obj.__name__))
        elif issubclass(obj, Enum) and obj is not Enum:
            found.add((obj.__module__, obj.__name__))
    return found


def collect_plugin_serde_modules(plugins: list[Any] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for plugin in plugins or []:
        for module_name in plugin.checkpoint_serde_modules():
            if module_name not in seen:
                seen.add(module_name)
                ordered.append(module_name)
    return tuple(ordered)


def collect_checkpoint_allowlist(
    plugins: list[Any] | None = None,
    *,
    extra_modules: tuple[str, ...] = (),
) -> tuple[tuple[str, str], ...]:
    """Merge core modules, plugin-declared modules, and extra types into one allowlist."""
    modules: list[str] = list(CORE_CHECKPOINT_MODULES)
    modules.extend(collect_plugin_serde_modules(plugins))
    modules.extend(extra_modules)

    allowlist: set[tuple[str, str]] = set(_EXTRA_CHECKPOINT_TYPES)
    for module_name in modules:
        try:
            allowlist.update(collect_types_from_module(module_name))
        except Exception as exc:
            log.error("checkpoint_serde_module_scan_failed", module=module_name, error=str(exc))
            raise

    return tuple(sorted(allowlist))


def build_checkpoint_serde(plugins: list[Any] | None = None) -> JsonPlusSerializer:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    allowlist = collect_checkpoint_allowlist(plugins)
    log.info(
        "checkpoint_serde_built",
        type_count=len(allowlist),
        plugin_modules=list(collect_plugin_serde_modules(plugins)),
    )
    return JsonPlusSerializer(allowed_msgpack_modules=allowlist)
