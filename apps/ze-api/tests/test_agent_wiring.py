import importlib

from ze_agents.registry import get_registered_agents

from tests.support.agent_modules import ALL_AGENT_MODULE_PATHS


def test_agents_registered_via_agent_decorator():
    for path in ALL_AGENT_MODULE_PATHS:
        importlib.import_module(path)
    agents = get_registered_agents()
    assert "research" in agents
    assert "companion" in agents
    assert "calendar" in agents
    assert "email" in agents
    assert "workflow" in agents
    assert "goals" in agents
    research = agents["research"]
    assert getattr(research, "description", "").strip()
    assert getattr(research, "model", "")
