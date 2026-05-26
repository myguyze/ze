import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.errors import RoutingError
from ze_core.orchestration import agent, clear_registry
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.routing.haiku_fallback import decompose


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


def _register(name: str, intent_map: dict | None = None) -> None:
    class _A:
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response="")

    _A.__name__ = f"Agent_{name}"
    _A.name = name
    _A.description = f"The {name} agent"
    _A.enabled = True
    _A.intent_map = intent_map or {}
    agent(_A)


def _registry_from_names(*names: str) -> dict:
    from ze_core.orchestration.registry import get_enabled_agents
    return get_enabled_agents()


def _mock_client(response: str) -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return client


class TestDecomposeSingleAgent:
    async def test_returns_single_subtask(self):
        _register("research")
        payload = json.dumps({"subtasks": [{"agent": "research", "intent": "read", "prompt": "find X"}], "sequential": False})
        client = _mock_client(payload)
        env = await decompose("find X", {}, client, _registry_from_names("research"), "haiku")
        assert env.primary_agent == "research"
        assert len(env.subtasks) == 1
        assert env.routing_method == "haiku"
        assert not env.is_compound

    async def test_populates_confidence_from_raw_scores(self):
        _register("research")
        payload = json.dumps({"subtasks": [{"agent": "research", "intent": "read", "prompt": "q"}], "sequential": False})
        client = _mock_client(payload)
        env = await decompose("q", {"research": 0.72}, client, _registry_from_names(), "haiku")
        assert env.confidence == pytest.approx(0.72)


class TestDecomposeCompound:
    async def test_compound_non_sequential(self):
        _register("research")
        _register("calendar")
        payload = json.dumps({
            "subtasks": [
                {"agent": "research", "intent": "read", "prompt": "research X"},
                {"agent": "calendar", "intent": "create", "prompt": "create event"},
            ],
            "sequential": False,
        })
        client = _mock_client(payload)
        env = await decompose("research X and create event", {}, client, _registry_from_names(), "haiku")
        assert env.is_compound
        assert env.requires_synthesis
        assert not env.is_sequential

    async def test_compound_sequential(self):
        _register("research")
        _register("calendar")
        payload = json.dumps({
            "subtasks": [
                {"agent": "research", "intent": "read", "prompt": "research X"},
                {"agent": "calendar", "intent": "create", "prompt": "create event"},
            ],
            "sequential": True,
        })
        client = _mock_client(payload)
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        assert env.is_sequential
        assert not env.requires_synthesis


class TestErrorHandling:
    async def test_unknown_agent_raises_immediately(self):
        _register("research")
        payload = json.dumps({"subtasks": [{"agent": "ghost", "intent": "read", "prompt": "q"}], "sequential": False})
        client = _mock_client(payload)
        with pytest.raises(RoutingError, match="unknown agent"):
            await decompose("q", {}, client, _registry_from_names(), "haiku")

    async def test_invalid_json_retries_then_hard_fallback(self):
        _register("research", intent_map={"reason": "Reasoning"})
        client = _mock_client("not json at all")
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        assert env.routing_method == "haiku_fallback"
        assert client.complete.call_count == 2

    async def test_empty_subtasks_retries_then_hard_fallback(self):
        _register("research", intent_map={"reason": "Reasoning"})
        payload = json.dumps({"subtasks": [], "sequential": False})
        client = _mock_client(payload)
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        assert env.routing_method == "haiku_fallback"

    async def test_hard_fallback_prefers_reason_agent(self):
        _register("alpha")
        _register("beta", intent_map={"reason": "Reasoning"})
        client = _mock_client("not json")
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        assert env.primary_agent == "beta"
        assert env.subtasks[0].intent == "reason"

    async def test_hard_fallback_uses_first_agent_if_no_reason(self):
        _register("alpha")
        _register("beta")
        client = _mock_client("not json")
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        # first alphabetically
        assert env.primary_agent == "alpha"


class TestMarkdownFenceStripping:
    async def test_strips_markdown_code_fence(self):
        _register("research")
        payload = '```json\n{"subtasks": [{"agent": "research", "intent": "read", "prompt": "q"}], "sequential": false}\n```'
        client = _mock_client(payload)
        env = await decompose("q", {}, client, _registry_from_names(), "haiku")
        assert env.primary_agent == "research"
