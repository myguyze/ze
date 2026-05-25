import importlib
import inspect
from pathlib import Path
from typing import Any, get_type_hints

import asyncpg
from tavily import AsyncTavilyClient

from ze.agents.registry import _registry, register_instance
from ze.browser.client import BrowserClient
from ze.contacts.channel_store import ContactChannelStore
from ze.contacts.store import PersonStore
from ze.errors import AgentConfigError
from ze.goals.executor import GoalExecutor
from ze.goals.planner import GoalPlanner
from ze.goals.store import GoalStore
from ze.google.auth import GoogleCredentials
from ze.openrouter.client import OpenRouterClient
from ze.proactive.notifier import ProactiveNotifier
from ze.reminders.store import ReminderStore
from ze.settings import Settings
from ze.workflow.planner import WorkflowPlanner
from ze.workflow.scheduler import WorkflowScheduler
from ze.workflow.store import WorkflowStore

_dep_map: dict[type, Any] = {}

_AGENTS_DIR = Path(__file__).parent


def bootstrap_agents(
    *,
    openrouter_client: OpenRouterClient,
    settings: Settings,
    tavily_client: AsyncTavilyClient | None = None,
    google_credentials: GoogleCredentials | None = None,
    workflow_store: WorkflowStore | None = None,
    workflow_planner: WorkflowPlanner | None = None,
    workflow_scheduler: WorkflowScheduler | None = None,
    reminder_store: ReminderStore | None = None,
    notifier: ProactiveNotifier | None = None,
    person_store: PersonStore | None = None,
    browser_client: BrowserClient | None = None,
    contact_channel_store: ContactChannelStore | None = None,
    goal_store: GoalStore | None = None,
    goal_planner: GoalPlanner | None = None,
    goal_executor: GoalExecutor | None = None,
    pool: asyncpg.Pool | None = None,
) -> None:
    """Instantiate and register all enabled agents. Called once at app startup."""
    if tavily_client is None:
        tavily_client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    if google_credentials is None:
        google_credentials = GoogleCredentials.from_settings(settings)

    _dep_map.clear()
    _dep_map[OpenRouterClient]   = openrouter_client
    _dep_map[Settings]           = settings
    _dep_map[AsyncTavilyClient]  = tavily_client
    _dep_map[GoogleCredentials]  = google_credentials

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
        _dep_map[PersonStore] = person_store
    if browser_client is not None:
        _dep_map[BrowserClient] = browser_client
    if contact_channel_store is not None:
        _dep_map[ContactChannelStore] = contact_channel_store
    if goal_store is not None:
        _dep_map[GoalStore] = goal_store
    if goal_planner is not None:
        _dep_map[GoalPlanner] = goal_planner
    if goal_executor is not None:
        _dep_map[GoalExecutor] = goal_executor
    if pool is not None:
        _dep_map[asyncpg.Pool] = pool

    _import_agent_modules()

    for name, cls in _registry.items():
        agent_cfg = settings.agent_configs.get(name, {})
        if not agent_cfg.get("enabled", True):
            continue
        instance = _resolve(cls)
        register_instance(name, instance)

    validate_registry(settings)


def validate_registry(settings: Settings) -> None:
    """Cross-check declared tools and intent_map entries against registries.

    Raises AgentConfigError on the first inconsistency found — misconfigured
    agents must not reach a running server.
    """
    from ze.agents.tool import registered_tools

    tool_reg = registered_tools()

    for name, cls in _registry.items():
        declared_tools: list[str] = getattr(cls, "tools", [])
        agent_cfg = settings.agent_configs.get(name, {})
        agent_cap: dict = agent_cfg.get("capabilities", {})
        intent_map: dict = agent_cfg.get("intent_map", {})

        for tool_name in declared_tools:
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {name!r} declares unknown tool {tool_name!r}. "
                    f"Ensure the agent's tools module is imported at startup."
                )

        for intent in intent_map:
            if intent not in agent_cap:
                raise AgentConfigError(
                    f"Agent {name!r} declares intent {intent!r} in its YAML "
                    f"intent_map but {intent!r} is missing from config.yaml capabilities."
                )


# ── Private ───────────────────────────────────────────────────────────────────

def _import_agent_modules() -> None:
    """Import shared tools then every agent sub-package that has an agent.py."""
    importlib.import_module("ze.tools")  # shared tools — always registered
    for path in sorted(_AGENTS_DIR.iterdir()):
        if path.is_dir() and (path / "agent.py").exists():
            importlib.import_module(f"ze.agents.{path.name}.agent")


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
