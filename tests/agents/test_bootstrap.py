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
    )

    assert isinstance(get_agent("companion"), CompanionAgent)
    assert isinstance(get_agent("research"), ResearchAgent)
