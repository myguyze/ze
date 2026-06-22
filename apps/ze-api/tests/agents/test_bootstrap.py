import pathlib
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from ze_agents.bootstrap import bootstrap_agents
from ze_personal.agents.companion.agent import CompanionAgent
from ze_agents.registry import _instances, get_agent
from ze_personal.agents.research.agent import ResearchAgent
from ze_api.logging import configure_logging
from ze_api.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture(autouse=True)
def clean_instances():
    before = dict(_instances)
    yield
    _instances.clear()
    _instances.update(before)


@pytest.fixture
def settings(tmp_path):
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def test_bootstrap_registers_companion_and_research(settings):
    from unittest.mock import MagicMock as MM
    from ze_browser import BrowserClient
    from ze_personal.contacts.store import PersonStore
    from ze_personal.contacts.channel_store import ContactChannelStore
    from ze_automation.goals.executor import GoalExecutor
    from ze_automation.goals.planner import GoalPlanner
    from ze_automation.goals.postgres import PostgresGoalStore
    from ze_agents.client import LLMClient
    from ze_calendar.reminders.store import ReminderStore
    from ze_automation.workflow.store import WorkflowStore
    from ze_automation.workflow.planner import WorkflowPlanner
    from ze_automation.workflow.scheduler import WorkflowScheduler
    from ze_prospecting.store import ProspectCampaignStore
    from ze_prospecting.types import ProspectingSettings
    from ze_core.openrouter.client import OpenRouterClient
    from ze_google.auth import GoogleCredentials
    from ze_agents.settings import Settings as CoreSettings
    from ze_proactive.notifier import ProactiveNotifier

    class _AllPathsPlugin:
        def agent_module_paths(self) -> list[str]:
            from tests.support.agent_modules import ALL_AGENT_MODULE_PATHS
            return list(ALL_AGENT_MODULE_PATHS)

    client = AsyncMock()
    core_settings = settings.to_core_settings()
    deps = {
        LLMClient: client,
        OpenRouterClient: client,
        CoreSettings: core_settings,
        asyncpg.Pool: MagicMock(),
        WorkflowStore: MM(spec=WorkflowStore),
        WorkflowPlanner: MM(spec=WorkflowPlanner),
        WorkflowScheduler: MM(spec=WorkflowScheduler),
        ReminderStore: MM(spec=ReminderStore),
        PersonStore: MM(spec=PersonStore),
        ContactChannelStore: MM(spec=ContactChannelStore),
        BrowserClient: MM(spec=BrowserClient),
        PostgresGoalStore: MM(spec=PostgresGoalStore),
        GoalPlanner: MM(spec=GoalPlanner),
        GoalExecutor: MM(spec=GoalExecutor),
        ProspectCampaignStore: MM(spec=ProspectCampaignStore),
        ProspectingSettings: ProspectingSettings(),
        GoogleCredentials: MM(spec=GoogleCredentials),
        ProactiveNotifier: MM(spec=ProactiveNotifier),
        object: client,
    }
    bootstrap_agents(deps=deps, plugins=[_AllPathsPlugin()])

    assert isinstance(get_agent("companion"), CompanionAgent)
    assert isinstance(get_agent("research"), ResearchAgent)
