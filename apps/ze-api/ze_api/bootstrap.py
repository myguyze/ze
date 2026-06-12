from __future__ import annotations

import importlib
import inspect
import sys
import types as _types
import typing
from typing import Any, get_type_hints

import asyncpg

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
    loads each class, and instantiates it via ``_resolve()`` using the provided
    (or module-level) dep_map.

    Returns the ordered list of plugin instances. Logs every discovered and
    instantiated plugin at INFO level.
    """
    from importlib.metadata import entry_points

    effective_deps = dep_map if dep_map is not None else _dep_map
    discovered: list[ZePlugin] = []

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

        instance = _resolve(cls, effective_deps)
        log.info("plugin_instantiated", name=ep.name, cls=cls.__qualname__)
        discovered.append(instance)

    if not discovered:
        log.warning("no_plugins_discovered")
    return discovered


def bootstrap_agents(
    *,
    deps: dict[type, Any] | None = None,
    plugins: list[ZePlugin] | None = None,
    # Legacy kwargs — forwarded into deps for backwards compatibility.
    openrouter_client: Any = None,
    settings: Any = None,
    google_credentials: Any = None,
    workflow_store: Any = None,
    workflow_planner: Any = None,
    workflow_scheduler: Any = None,
    reminder_store: Any = None,
    notifier: Any = None,
    person_store: Any = None,
    browser_client: Any = None,
    contact_channel_store: Any = None,
    goal_store: Any = None,
    goal_planner: Any = None,
    goal_executor: Any = None,
    pool: asyncpg.Pool | None = None,
    campaign_store: Any = None,
    prospecting_settings: Any = None,
    memory_store: Any = None,
    news_store: Any = None,
) -> None:
    """Instantiate and register all enabled agents. Called once at app startup.

    Prefer passing ``deps`` as a typed dict. The individual keyword arguments
    are kept for backwards compatibility and are merged into ``deps``.
    """
    from ze_google.auth import GoogleCredentials
    from ze_agents.client import LLMClient
    from ze_core.openrouter.client import OpenRouterClient
    from ze_api.settings import Settings
    from ze_agents.settings import Settings as CoreSettings

    _dep_map.clear()

    # Start from the explicit deps dict.
    if deps:
        _dep_map.update(deps)

    # Resolve google_credentials from settings if not explicitly provided.
    if google_credentials is None and settings is not None:
        google_credentials = GoogleCredentials.from_settings(settings)

    # Merge legacy kwargs.
    _legacy: list[tuple[Any, Any]] = [
        (OpenRouterClient, openrouter_client),
        (LLMClient, openrouter_client),
        (Settings, settings),
        (CoreSettings, settings.to_core_settings() if settings and hasattr(settings, "to_core_settings") else None),
        (GoogleCredentials, google_credentials),
        (asyncpg.Pool, pool),
    ]
    for type_, val in _legacy:
        if val is not None:
            _dep_map[type_] = val

    # Optional typed deps — only add if provided.
    _optional: list[tuple[str, Any]] = [
        ("ze_personal.workflow.store.WorkflowStore", workflow_store),
        ("ze_personal.workflow.planner.WorkflowPlanner", workflow_planner),
        ("ze_personal.workflow.scheduler.WorkflowScheduler", workflow_scheduler),
        ("ze_calendar.reminders.store.ReminderStore", reminder_store),
        ("ze_proactive.notifier.ProactiveNotifier", notifier),
        ("ze_proactive.push_log_store.PushLogStore", notifier and getattr(notifier, "_push_log_store", None)),
        ("ze_personal.contacts.store.PersonStore", person_store),
        ("ze_browser.BrowserClient", browser_client),
        ("ze_personal.contacts.channel_store.ContactChannelStore", contact_channel_store),
        ("ze_personal.goals.postgres.PostgresGoalStore", goal_store),
        ("ze_personal.goals.planner.GoalPlanner", goal_planner),
        ("ze_personal.goals.executor.GoalExecutor", goal_executor),
        ("ze_prospecting.store.ProspectCampaignStore", campaign_store),
        ("ze_prospecting.types.ProspectingSettings", prospecting_settings),
        ("ze_memory.retriever.PostgresMemoryStore", memory_store),
    ]
    for dotted, val in _optional:
        if val is not None:
            try:
                mod, attr = dotted.rsplit(".", 1)
                type_ = getattr(importlib.import_module(mod), attr)
                _dep_map[type_] = val
            except Exception:
                pass  # package not installed — skip silently

    if goal_store is not None and news_store is not None:
        try:
            from ze_news.types import GoalTitleProvider
            _dep_map[GoalTitleProvider] = goal_store
        except ImportError:
            pass
    if news_store is not None:
        try:
            from ze_news.store import NewsStore
            _dep_map[NewsStore] = news_store
        except ImportError:
            pass

    for module_path in _plugin_agent_module_paths(plugins):
        log.debug("importing_agent_module", path=module_path)
        importlib.import_module(module_path)

    prepare_gate_registry(settings, plugins)

    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls)
        register_instance(name, instance)
        log.debug("agent_registered", name=name, cls=cls.__name__)

    validate_registry()
    log.info("bootstrap_complete", agents=list(get_registered_agents()))


def prepare_gate_registry(settings: Any, plugins: list | None = None) -> None:
    del settings, plugins


def validate_registry() -> None:
    """Cross-check declared tools and intent_map entries against registries."""
    from ze_agents.tool import registered_tools

    tool_reg = registered_tools()

    for name, cls in get_registered_agents().items():
        declared_tools: list[str] = getattr(cls, "tools", [])
        capabilities: dict = getattr(cls, "capabilities", {})
        intent_map: dict = getattr(cls, "intent_map", {})

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

        if capabilities:
            for intent in intent_map:
                if intent not in capabilities:
                    raise AgentConfigError(
                        f"Agent {name!r} declares intent {intent!r} in intent_map "
                        f"but {intent!r} is missing from capabilities."
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


def _import_agent_modules(plugins: list | None = None) -> None:
    for module_path in _DEFAULT_AGENT_MODULE_PATHS:
        importlib.import_module(module_path)


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


def _resolve(cls: type, dep_map: dict | None = None) -> object:
    """Instantiate cls by matching __init__ parameter types against dep_map.

    Parameters with defaults are skipped when their type is not registered —
    the default value is used instead. This supports Optional[T] and T | None
    annotations, including GoogleCredentials | None patterns used in plugins.
    """
    effective = dep_map if dep_map is not None else _dep_map

    try:
        hints = get_type_hints(cls.__init__)
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
