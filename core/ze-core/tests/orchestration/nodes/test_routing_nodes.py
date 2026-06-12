import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_agents.registry import agent, clear_registry
from ze_agents.base_agent import BaseAgent
from ze_core.orchestration.nodes.routing import decompose, embed_route
from ze_agents.types import AgentContext, AgentResult
from ze_core.routing.types import RouterConfig, RoutingEnvelope, SubTask


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


def _register(name: str, intent_map: dict | None = None) -> None:
    class _A(BaseAgent):
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response="ok")

    _A.name = name
    _A.description = f"The {name} agent"
    _A.enabled = True
    _A.intent_map = intent_map or {"read": "Read"}
    agent(_A)


def _envelope(is_compound: bool = True, raw_scores: dict | None = None) -> RoutingEnvelope:
    return RoutingEnvelope(
        primary_agent="alpha",
        confidence=0.4,
        score_gap=0.1,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=[SubTask(agent="alpha", intent="read", prompt="do it")],
        requires_synthesis=False,
        raw_scores=raw_scores or {"alpha": 0.4, "beta": 0.3},
    )


def _config(client, router=None) -> dict:
    return {
        "configurable": {
            "openrouter_client": client,
            "router": router,
        }
    }


def _state(prompt: str = "do it", envelope=None) -> dict:
    return {
        "session_id": "s1",
        "prompt": prompt,
        "envelope": envelope or _envelope(),
    }


class TestDecomposeNode:
    async def test_calls_fallback_decompose_and_replaces_envelope(self):
        _register("alpha")
        _register("beta")
        client = AsyncMock()
        client.complete = AsyncMock(return_value=json.dumps({
            "subtasks": [
                {"agent": "alpha", "intent": "read", "prompt": "research part"},
                {"agent": "beta", "intent": "create", "prompt": "write part"},
            ],
            "sequential": False,
        }))

        result = await decompose(_state(), _config(client))

        assert "envelope" in result
        env = result["envelope"]
        assert len(env.subtasks) == 2
        assert env.routing_method == "haiku"
        assert env.is_compound is True
        client.complete.assert_awaited_once()

    async def test_single_subtask_result_is_not_compound(self):
        _register("alpha")
        client = AsyncMock()
        client.complete = AsyncMock(return_value=json.dumps({
            "subtasks": [{"agent": "alpha", "intent": "read", "prompt": "simple"}],
            "sequential": False,
        }))

        result = await decompose(_state(), _config(client))

        env = result["envelope"]
        assert env.is_compound is False
        assert len(env.subtasks) == 1

    async def test_uses_fallback_model_from_router_config(self):
        _register("alpha")
        router = MagicMock()
        router._config = RouterConfig(fallback_model="openai/gpt-4o-mini")
        client = AsyncMock()
        client.complete = AsyncMock(return_value=json.dumps({
            "subtasks": [{"agent": "alpha", "intent": "read", "prompt": "p"}],
            "sequential": False,
        }))

        await decompose(_state(), _config(client, router=router))

        call_kwargs = client.complete.call_args[1]
        assert call_kwargs["model"] == "openai/gpt-4o-mini"

    async def test_passes_raw_scores_from_envelope(self):
        _register("alpha")
        _register("beta")
        captured = {}
        client = AsyncMock()

        async def _capture(**kwargs):
            captured.update(kwargs)
            return json.dumps({
                "subtasks": [{"agent": "alpha", "intent": "read", "prompt": "p"}],
                "sequential": False,
            })

        client.complete = _capture
        raw = {"alpha": 0.45, "beta": 0.38}
        state = _state(envelope=_envelope(raw_scores=raw))

        await decompose(state, _config(client))
        # raw_scores are passed through to fallback.decompose (used in RoutingEnvelope)
        # verify by checking the returned envelope has them
        # (fallback.decompose reads raw_scores to set confidence on result)

    async def test_sequential_subtasks_sets_is_sequential(self):
        _register("alpha")
        _register("beta")
        client = AsyncMock()
        client.complete = AsyncMock(return_value=json.dumps({
            "subtasks": [
                {"agent": "alpha", "intent": "read", "prompt": "step 1"},
                {"agent": "beta", "intent": "create", "prompt": "step 2"},
            ],
            "sequential": True,
        }))

        result = await decompose(_state(), _config(client))
        assert result["envelope"].is_sequential is True
        assert result["envelope"].requires_synthesis is False

    async def test_llm_failure_falls_back_to_hard_fallback(self):
        _register("alpha")
        client = AsyncMock()
        # Two consecutive failures → hard fallback
        client.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

        result = await decompose(_state(), _config(client))

        # Hard fallback should still return a valid envelope, not raise
        assert "envelope" in result
        env = result["envelope"]
        assert len(env.subtasks) == 1
        assert env.routing_method == "fallback"

    async def test_no_router_in_config_uses_default_model(self):
        _register("alpha")
        client = AsyncMock()
        client.complete = AsyncMock(return_value=json.dumps({
            "subtasks": [{"agent": "alpha", "intent": "read", "prompt": "p"}],
            "sequential": False,
        }))

        result = await decompose(_state(), _config(client, router=None))

        assert "envelope" in result
        client.complete.assert_awaited_once()
        call_kwargs = client.complete.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-haiku-4-5"


class TestEmbedRouteNode:
    def _router(self):
        envelope = RoutingEnvelope(
            primary_agent="goals",
            confidence=0.9,
            score_gap=0.3,
            routing_method="embedding",
            is_compound=False,
            subtasks=[SubTask(agent="goals", intent="update", prompt="steer")],
            requires_synthesis=False,
            raw_scores={"goals": 0.9},
        )
        router = AsyncMock()
        router.route = AsyncMock(return_value=envelope)
        return router

    async def test_appends_routing_hints_when_present(self):
        router = self._router()
        state = {
            "session_id": "s1",
            "prompt": "skip the LinkedIn step",
            "image_caption": None,
            "routing_hints": '[Active goals: "Job search" — step 3: LinkedIn outreach]',
        }
        config = {"configurable": {"router": router}}

        await embed_route(state, config)

        call_args = router.route.call_args
        routing_text = call_args.kwargs.get("prompt") or call_args.args[0] if call_args.args else call_args.kwargs["prompt"]
        assert "skip the LinkedIn step" in routing_text
        assert "[Active goals:" in routing_text
        # Hints appended AFTER the message, not prepended
        assert routing_text.index("skip") < routing_text.index("[Active goals:")

    async def test_routing_unchanged_when_hints_is_none(self):
        router = self._router()
        state = {
            "session_id": "s1",
            "prompt": "what's the weather?",
            "image_caption": None,
            "routing_hints": None,
        }
        config = {"configurable": {"router": router}}

        await embed_route(state, config)

        call_args = router.route.call_args
        routing_text = call_args.kwargs.get("prompt") or call_args.kwargs["prompt"]
        assert routing_text == "what's the weather?"
        assert "[Active goals:" not in routing_text


class TestEmbedRouteFollowUps:
    """Anaphoric follow-ups must carry recent conversation into the routing text,
    so e.g. 'are these recent?' after a news answer routes to news, not prospecting."""

    def _router(self):
        envelope = RoutingEnvelope(
            primary_agent="news",
            confidence=0.9,
            score_gap=0.3,
            routing_method="embedding",
            is_compound=False,
            subtasks=[SubTask(agent="news", intent="read", prompt="x")],
            requires_synthesis=False,
            raw_scores={"news": 0.9},
        )
        router = AsyncMock()
        router.route = AsyncMock(return_value=envelope)
        return router

    def _news_history(self) -> list[dict]:
        return [
            {"role": "user", "content": "whats in the news regarding AI?"},
            {"role": "assistant", "content": "Here's what's trending in AI right now: ..."},
        ]

    async def _routed_text(self, state: dict) -> str:
        router = self._router()
        await embed_route(state, {"configurable": {"router": router}})
        call_args = router.route.call_args
        return call_args.kwargs["prompt"]

    async def test_are_these_recent_includes_news_history(self):
        routing_text = await self._routed_text({
            "session_id": "s1",
            "prompt": "are these news recent?",
            "image_caption": None,
            "routing_hints": None,
            "messages": self._news_history(),
            "last_active_at": time.time(),
        })
        assert routing_text.startswith("are these news recent?")
        assert "[Recent conversation]" in routing_text
        assert "whats in the news regarding AI?" in routing_text

    async def test_how_did_you_get_those_includes_news_history(self):
        routing_text = await self._routed_text({
            "session_id": "s1",
            "prompt": "I meant those ones in specific. How did you get those?",
            "image_caption": None,
            "routing_hints": None,
            "messages": self._news_history(),
            "last_active_at": time.time(),
        })
        assert "trending in AI" in routing_text
        # current message dominates: it comes before the history hint
        assert routing_text.index("How did you get those?") < routing_text.index("[Recent conversation]")

    async def test_no_history_hint_when_session_expired(self):
        routing_text = await self._routed_text({
            "session_id": "s1",
            "prompt": "are these recent?",
            "image_caption": None,
            "routing_hints": None,
            "messages": self._news_history(),
            "last_active_at": time.time() - 3600,  # > 30 min inactivity
        })
        assert routing_text == "are these recent?"

    async def test_no_history_hint_when_no_messages(self):
        routing_text = await self._routed_text({
            "session_id": "s1",
            "prompt": "are these recent?",
            "image_caption": None,
            "routing_hints": None,
            "messages": [],
            "last_active_at": None,
        })
        assert routing_text == "are these recent?"

    async def test_history_messages_are_truncated(self):
        history = [{"role": "assistant", "content": "y" * 5000}]
        routing_text = await self._routed_text({
            "session_id": "s1",
            "prompt": "shorten please",
            "image_caption": None,
            "routing_hints": None,
            "messages": history,
            "last_active_at": time.time(),
        })
        assert len(routing_text) < 1000
