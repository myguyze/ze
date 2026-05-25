import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.agents.bootstrap import bootstrap_agents
from ze.agents.companion.agent import CompanionAgent
from ze.agents.registry import _instances, get_agent
from ze.agents.research.agent import ResearchAgent
from ze.logging import configure_logging
from ze.settings import Settings, get_settings


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
    from ze.browser.client import BrowserClient
    from ze.contacts.store import PersonStore
    from ze.goals.executor import GoalExecutor
    from ze.goals.planner import GoalPlanner
    from ze.goals.store import GoalStore
    from ze.proactive.notifier import ProactiveNotifier
    from ze.reminders.store import ReminderStore
    from ze.workflow.store import WorkflowStore
    from ze.workflow.planner import WorkflowPlanner
    from ze.workflow.scheduler import WorkflowScheduler

    client = AsyncMock()
    tavily = MagicMock()
    bootstrap_agents(
        openrouter_client=client,
        settings=settings,
        tavily_client=tavily,
        workflow_store=MM(spec=WorkflowStore),
        workflow_planner=MM(spec=WorkflowPlanner),
        workflow_scheduler=MM(spec=WorkflowScheduler),
        reminder_store=MM(spec=ReminderStore),
        notifier=MM(spec=ProactiveNotifier),
        person_store=MM(spec=PersonStore),
        browser_client=MM(spec=BrowserClient),
        goal_store=MM(spec=GoalStore),
        goal_planner=MM(spec=GoalPlanner),
        goal_executor=MM(spec=GoalExecutor),
        pool=MagicMock(),
    )

    assert isinstance(get_agent("companion"), CompanionAgent)
    assert isinstance(get_agent("research"), ResearchAgent)
