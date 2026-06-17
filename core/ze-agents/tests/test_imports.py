def test_public_api_imports() -> None:
    from ze_agents.base_agent import BaseAgent
    from ze_agents.registry import agent
    from ze_agents.tool import tool

    assert callable(agent)
    assert callable(tool)
    assert BaseAgent is not None
