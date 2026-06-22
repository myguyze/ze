import pytest

from ze_agents.bootstrap import reload_agent_modules

from tests.support.agent_modules import ALL_AGENT_MODULE_PATHS


@pytest.fixture(autouse=True)
def _load_routing_agent_registry():
    reload_agent_modules(ALL_AGENT_MODULE_PATHS)
