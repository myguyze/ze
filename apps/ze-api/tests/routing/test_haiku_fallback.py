import json
import pytest
from unittest.mock import AsyncMock

from ze_api.bootstrap import prepare_gate_registry
from ze_core.errors import RoutingError
from ze_api.logging import configure_logging
from ze_core.orchestration.registry import get_enabled_agents
from ze_core.routing.fallback import decompose as _decompose
from ze_core.routing.types import RoutingEnvelope


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture
def settings(tmp_path):
    import pathlib
    from ze_api.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    settings = Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )
    prepare_gate_registry(settings)
    return settings


def make_client(response: str) -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return client


async def decompose(prompt, raw_scores, client, settings):
    routing_cfg = settings.routing_config
    fallback_model = routing_cfg.get("fallback_model", "anthropic/claude-haiku-4-5")
    return await _decompose(
        prompt=prompt,
        raw_scores=raw_scores,
        client=client,
        agent_registry=get_enabled_agents(),
        fallback_model=fallback_model,
    )


def single_subtask_response(agent="research", intent="read", prompt="find it") -> str:
    return json.dumps({
        "subtasks": [{"agent": agent, "intent": intent, "prompt": prompt}]
    })


def compound_response() -> str:
    return json.dumps({
        "subtasks": [
            {"agent": "research", "intent": "read", "prompt": "search part"},
            {"agent": "companion", "intent": "reason", "prompt": "reasoning part"},
        ]
    })


# ── Single-agent ──────────────────────────────────────────────────────────────

async def test_decompose_single_subtask(settings):
    client = make_client(single_subtask_response())
    env = await decompose("find AI news", raw_scores={}, client=client, settings=settings)

    assert client.complete.await_args.kwargs["response_format"] == {"type": "json_object"}
    assert isinstance(env, RoutingEnvelope)
    assert env.routing_method == "haiku"
    assert env.is_compound is False
    assert env.requires_synthesis is False
    assert len(env.subtasks) == 1
    assert env.subtasks[0].agent == "research"
    assert env.subtasks[0].intent == "read"


async def test_decompose_sets_primary_agent_from_first_subtask(settings):
    client = make_client(compound_response())
    env = await decompose("compound", raw_scores={}, client=client, settings=settings)

    assert env.primary_agent == "research"


async def test_decompose_compound_task(settings):
    client = make_client(compound_response())
    env = await decompose("compound", raw_scores={}, client=client, settings=settings)

    assert env.is_compound is True
    assert env.requires_synthesis is True
    assert len(env.subtasks) == 2


async def test_decompose_passes_raw_scores_through(settings):
    raw = {"research": 0.4, "companion": 0.35}
    client = make_client(single_subtask_response())
    env = await decompose("hi", raw_scores=raw, client=client, settings=settings)

    assert env.raw_scores == raw


async def test_decompose_sets_confidence_from_raw_scores(settings):
    raw = {"research": 0.42, "companion": 0.38}
    client = make_client(single_subtask_response(agent="research"))
    env = await decompose("hi", raw_scores=raw, client=client, settings=settings)

    assert env.confidence == pytest.approx(0.42)


# ── Retry on bad JSON ─────────────────────────────────────────────────────────

async def test_decompose_retries_once_on_invalid_json(settings):
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=[
        "not json at all {{{{",
        single_subtask_response(),
    ])
    env = await decompose("hi", raw_scores={}, client=client, settings=settings)

    assert env.primary_agent == "research"
    assert client.complete.call_count == 2


async def test_decompose_hard_fallback_after_two_bad_responses(settings):
    client = make_client("not json")
    env = await decompose("hi", raw_scores={}, client=client, settings=settings)

    assert env.routing_method == "fallback"
    assert len(env.subtasks) == 1
    assert client.complete.call_count == 2


async def test_decompose_retries_on_missing_subtasks_key(settings):
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=[
        json.dumps({"result": []}),
        single_subtask_response(),
    ])
    env = await decompose("hi", raw_scores={}, client=client, settings=settings)

    assert env.primary_agent == "research"
    assert client.complete.call_count == 2


# ── Unknown agent guard ───────────────────────────────────────────────────────

async def test_decompose_raises_on_unknown_agent(settings):
    bad_response = json.dumps({
        "subtasks": [{"agent": "ghost_agent", "intent": "read", "prompt": "hi"}]
    })
    client = make_client(bad_response)
    with pytest.raises(RoutingError, match="unknown agent"):
        await decompose("hi", raw_scores={}, client=client, settings=settings)


# ── Score gap = 0.0 for haiku routes ─────────────────────────────────────────

async def test_decompose_score_gap_is_zero(settings):
    client = make_client(single_subtask_response())
    env = await decompose("hi", raw_scores={}, client=client, settings=settings)
    assert env.score_gap == 0.0
