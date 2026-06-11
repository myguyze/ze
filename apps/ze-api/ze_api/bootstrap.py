import importlib
import inspect
from typing import Any, get_type_hints

import asyncpg

from ze_core.errors import AgentConfigError
from ze_google.auth import GoogleCredentials
from ze_core.openrouter.client import OpenRouterClient
from ze_core.proactive.notifier import ProactiveNotifier
from ze_calendar.reminders.store import ReminderStore
from ze_api.settings import Settings
from ze_core.settings import Settings as CoreSettings
from ze_personal.workflow.planner import WorkflowPlanner
from ze_personal.workflow.store import WorkflowStore
from ze_personal.workflow.scheduler import WorkflowScheduler
from ze_core.orchestration.registry import (
    get_registered_agents,
    register_instance,
)

_dep_map: dict[type, Any] = {}

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


def prepare_gate_registry(settings: Settings, plugins: list | None = None) -> None:
    """Import agent modules so @agent registers classes in ze-core."""
    del settings, plugins


def bootstrap_agents(
    *,
    openrouter_client: OpenRouterClient,
    settings: Settings,
    google_credentials: GoogleCredentials | None = None,
    workflow_store: WorkflowStore | None = None,
    workflow_planner: WorkflowPlanner | None = None,
    workflow_scheduler: WorkflowScheduler | None = None,
    reminder_store: ReminderStore | None = None,
    notifier: ProactiveNotifier | None = None,
    person_store=None,
    browser_client=None,
    contact_channel_store=None,
    goal_store=None,
    goal_planner=None,
    goal_executor=None,
    pool: asyncpg.Pool | None = None,
    campaign_store=None,
    prospecting_settings=None,
    plugins: list | None = None,
    memory_store=None,
    news_store=None,
) -> None:
    """Instantiate and register all enabled agents. Called once at app startup."""
    if google_credentials is None:
        google_credentials = GoogleCredentials.from_settings(settings)

    _dep_map.clear()
    _dep_map[OpenRouterClient] = openrouter_client
    _dep_map[Settings] = settings
    _dep_map[CoreSettings] = settings.to_core_settings()
    _dep_map[GoogleCredentials] = google_credentials

    if workflow_store is not None:
        _dep_map[WorkflowStore] = workflow_store
    if workflow_planner is not None:
        _dep_map[WorkflowPlanner] = workflow_planner
    if workflow_scheduler is not None:
        _dep_map[WorkflowScheduler] = workflow_scheduler
    if reminder_store is not None:
        _dep_map[ReminderStore] = reminder_store
    if notifier is not None:
        _dep_map[ProactiveNotifier] = notifier
    if person_store is not None:
        from ze_personal.contacts.store import PersonStore
        _dep_map[PersonStore] = person_store
    if browser_client is not None:
        from ze_browser import BrowserClient
        _dep_map[BrowserClient] = browser_client
    if contact_channel_store is not None:
        from ze_personal.contacts.channel_store import ContactChannelStore
        _dep_map[ContactChannelStore] = contact_channel_store
    if goal_store is not None:
        from ze_personal.goals.postgres import PostgresGoalStore as GoalStore
        _dep_map[GoalStore] = goal_store
    if goal_planner is not None:
        from ze_personal.goals.planner import GoalPlanner
        _dep_map[GoalPlanner] = goal_planner
    if goal_executor is not None:
        from ze_personal.goals.executor import GoalExecutor
        _dep_map[GoalExecutor] = goal_executor
    if pool is not None:
        _dep_map[asyncpg.Pool] = pool
    if campaign_store is not None:
        from ze_prospecting.store import ProspectCampaignStore
        _dep_map[ProspectCampaignStore] = campaign_store
    if prospecting_settings is not None:
        from ze_prospecting.types import ProspectingSettings
        _dep_map[ProspectingSettings] = prospecting_settings
    if memory_store is not None:
        from ze_memory.retriever import PostgresMemoryStore
        _dep_map[PostgresMemoryStore] = memory_store
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
        importlib.import_module(module_path)

    prepare_gate_registry(settings, plugins)

    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls)
        register_instance(name, instance)

    validate_registry()


def validate_registry() -> None:
    """Cross-check declared tools and intent_map entries against registries."""
    from ze_core.orchestration.tool import registered_tools

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


def _plugin_agent_module_paths(plugins: list | None) -> list[str]:
    paths: list[str] = list(_DEFAULT_AGENT_MODULE_PATHS)
    for plugin in (plugins or []):
        paths.extend(plugin.agent_module_paths())
    return paths


def _import_agent_modules(plugins: list | None = None) -> None:
    """Import shared tools and plugin agent modules."""
    for module_path in _DEFAULT_AGENT_MODULE_PATHS:
        importlib.import_module(module_path)


def reload_agent_modules(plugins: list | None = None) -> None:
    """Force @agent registration after tests replace the ze-core registry."""
    import sys

    from ze_core.orchestration.registry import _instances, _registry
    from ze_core.orchestration.tool import clear_tool_registry

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


def _resolve(cls: type) -> object:
    """Instantiate cls by matching __init__ parameter types against _dep_map."""
    try:
        hints = get_type_hints(cls.__init__)
    except Exception as exc:
        raise AgentConfigError(
            f"Cannot resolve type hints for {cls.__name__}.__init__: {exc}"
        ) from exc

    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        annotation = hints.get(param_name)
        if annotation is None:
            raise AgentConfigError(
                f"{cls.__name__}.__init__ parameter {param_name!r} has no type annotation"
            )
        if annotation not in _dep_map:
            raise AgentConfigError(
                f"No dependency registered for type {annotation!r} "
                f"(required by {cls.__name__}). "
                f"Add it to _dep_map before calling bootstrap_agents()."
            )
        kwargs[param_name] = _dep_map[annotation]

    return cls(**kwargs)
