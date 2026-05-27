import json
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from ze.agents.bootstrap import prepare_gate_registry
from ze.errors import InvalidPromptError, RoutingError
from ze.logging import configure_logging
from ze.routing.router import EmbeddingRouter
from ze.routing.types import RouterConfig, RoutingEnvelope, SubTask


# ── Helpers ───────────────────────────────────────────────────────────────────

def unit_vec(size: int = 384) -> np.ndarray:
    v = np.random.randn(size).astype(np.float32)
    return v / np.linalg.norm(v)


def make_embedder(agent_vecs: dict[str, np.ndarray], prompt_vec: np.ndarray) -> MagicMock:
    """
    Returns a mock embedder whose encode() returns:
    - agent_vecs stacked in alphabetical agent-name order (matches ze-core router)
    - prompt_vec when called with a string (per-request encode)
    """
    mock = MagicMock()
    ordered = [agent_vecs[k] for k in sorted(agent_vecs)]

    def encode(text, **kwargs):
        if isinstance(text, list):
            return np.stack(ordered)
        return prompt_vec

    mock.encode.side_effect = encode
    return mock


def make_client(response: str = "{}") -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return client


def make_router(
    settings,
    embedder=None,
    client=None,
    prompt_vec=None,
) -> EmbeddingRouter:
    if embedder is None:
        _prompt_vec = prompt_vec or unit_vec()
        enabled = {
            name: cfg
            for name, cfg in settings.agent_configs.items()
            if cfg.get("enabled", True)
        }
        agent_vecs = {name: unit_vec() for name in enabled}
        embedder = make_embedder(agent_vecs, _prompt_vec)
    prepare_gate_registry(settings)
    _client = client or make_client()
    return EmbeddingRouter(
        embedder=embedder,
        openrouter_client=_client,
        routing_store=None,
        config=RouterConfig(),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── RoutingEnvelope / SubTask ─────────────────────────────────────────────────

def test_subtask_fields():
    st = SubTask(agent="research", intent="read", prompt="hello")
    assert st.agent == "research"
    assert st.intent == "read"
    assert st.prompt == "hello"


def test_routing_envelope_defaults():
    st = SubTask(agent="research", intent="read", prompt="hi")
    env = RoutingEnvelope(
        primary_agent="research",
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=False,
        subtasks=[st],
        requires_synthesis=False,
    )
    assert env.raw_scores == {}


# ── EmbeddingRouter construction ──────────────────────────────────────────────

def test_router_raises_if_no_enabled_agents(settings_factory):
    settings = settings_factory(disable_all=True)
    with pytest.raises(RoutingError, match="No enabled agents"):
        make_router(settings)


def test_router_loads_enabled_agents_only(two_agent_settings):
    router = make_router(two_agent_settings)
    assert set(router._agent_names) == {"companion", "research"}


# ── route() — invalid input ───────────────────────────────────────────────────

async def test_route_raises_on_empty_string(two_agent_settings):
    router = make_router(two_agent_settings)
    with pytest.raises(InvalidPromptError):
        await router.route("", session_id="s1")


async def test_route_raises_on_whitespace(two_agent_settings):
    router = make_router(two_agent_settings)
    with pytest.raises(InvalidPromptError):
        await router.route("   ", session_id="s1")


# ── route() — single-agent shortcut ──────────────────────────────────────────

async def test_single_agent_routes_directly(single_agent_settings):
    router = make_router(single_agent_settings)
    env = await router.route("search for news", session_id="s1")
    assert env.primary_agent == "research"
    assert env.routing_method == "embedding"
    assert env.confidence == 1.0
    assert len(env.subtasks) == 1
    assert env.is_compound is False


# ── route() — confident embedding routing ────────────────────────────────────

async def test_route_picks_highest_score_agent(two_agent_settings):
    research_vec = unit_vec()
    agent_vecs = {"research": research_vec, "companion": unit_vec()}
    embedder = make_embedder(agent_vecs=agent_vecs, prompt_vec=research_vec)
    router = make_router(two_agent_settings, embedder=embedder)
    env = await router.route("search the web", session_id="s1")

    assert env.primary_agent == "research"
    assert env.routing_method == "embedding"
    assert env.confidence > 0.9


async def test_route_returns_correct_subtask_structure(two_agent_settings):
    research_vec = unit_vec()
    agent_vecs = {"research": research_vec, "companion": unit_vec()}
    embedder = make_embedder(agent_vecs=agent_vecs, prompt_vec=research_vec)
    router = make_router(two_agent_settings, embedder=embedder)
    env = await router.route("find the latest AI research", session_id="s1")

    assert len(env.subtasks) == 1
    assert env.subtasks[0].agent == "research"
    assert env.subtasks[0].prompt == "find the latest AI research"


async def test_route_populates_raw_scores(two_agent_settings):
    research_vec = unit_vec()
    agent_vecs = {"research": research_vec, "companion": unit_vec()}
    embedder = make_embedder(agent_vecs=agent_vecs, prompt_vec=research_vec)
    router = make_router(two_agent_settings, embedder=embedder)
    env = await router.route("hello", session_id="s1")

    assert "research" in env.raw_scores
    assert "companion" in env.raw_scores


# ── route() — low confidence signals decompose (no inline Haiku) ─────────────

async def test_route_signals_decompose_when_score_below_threshold(two_agent_settings):
    low_vec = np.zeros(384, dtype=np.float32)
    low_vec[0] = 0.01

    agent_vecs = {"research": unit_vec(), "companion": unit_vec()}
    embedder = make_embedder(agent_vecs=agent_vecs, prompt_vec=low_vec)
    client = make_client()
    router = make_router(two_agent_settings, embedder=embedder, client=client)

    env = await router.route("something ambiguous", session_id="s1")

    assert env.is_compound is True
    assert env.routing_method == "embedding"
    client.complete.assert_not_awaited()


async def test_route_signals_decompose_when_gap_too_small(two_agent_settings):
    shared_base = unit_vec()

    def encode(text, **kwargs):
        if isinstance(text, list):
            return np.stack([shared_base, shared_base])
        return shared_base

    embedder = MagicMock()
    embedder.encode.side_effect = encode

    client = make_client()
    router = make_router(two_agent_settings, embedder=embedder, client=client)

    env = await router.route("compound task", session_id="s1")

    assert env.is_compound is True
    client.complete.assert_not_awaited()


# ── route() — prospecting agent ──────────────────────────────────────────────

async def test_route_picks_prospecting_as_single_agent(prospecting_only_settings):
    router = make_router(prospecting_only_settings)
    env = await router.route("find 5 charter operators in Portugal", session_id="s1")
    assert env.primary_agent == "prospecting"
    assert env.routing_method == "embedding"
    assert env.confidence == 1.0


async def test_route_picks_prospecting_over_research(prospecting_and_research_settings):
    prospecting_vec = unit_vec()
    agent_vecs = {"prospecting": prospecting_vec, "research": unit_vec()}
    embedder = make_embedder(agent_vecs=agent_vecs, prompt_vec=prospecting_vec)
    router = make_router(prospecting_and_research_settings, embedder=embedder)
    env = await router.route("build a prospect list of aviation CEOs in Europe", session_id="s1")
    assert env.primary_agent == "prospecting"
    assert env.confidence > 0.9


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def two_agent_settings(tmp_path):
    """Settings with only research + companion enabled."""
    return _make_settings(tmp_path, disable={"calendar", "email", "workflow", "reminders", "prospecting", "goals"})


@pytest.fixture
def single_agent_settings(tmp_path):
    """Settings with only research enabled."""
    return _make_settings(tmp_path, disable={"calendar", "email", "workflow", "companion", "reminders", "prospecting", "goals"})


@pytest.fixture
def prospecting_only_settings(tmp_path):
    """Settings with only prospecting enabled."""
    return _make_settings(tmp_path, disable={"calendar", "email", "workflow", "companion", "reminders", "research", "goals"})


@pytest.fixture
def prospecting_and_research_settings(tmp_path):
    """Settings with prospecting + research enabled."""
    return _make_settings(tmp_path, disable={"calendar", "email", "workflow", "companion", "reminders", "goals"})


@pytest.fixture
def settings_factory(tmp_path):
    def _factory(disable_all: bool = False):
        if disable_all:
            import pathlib
            import yaml
            real_config = pathlib.Path(__file__).parent.parent.parent / "config"
            with open(real_config / "config.yaml") as f:
                cfg = yaml.safe_load(f)
            disable = set(cfg.get("agents", {}).keys())
        else:
            disable = set()
        return _make_settings(tmp_path, disable=disable)
    return _factory


def _make_settings(tmp_path, disable: set[str]):
    import pathlib
    import shutil
    import yaml
    from ze.settings import Settings, get_settings

    get_settings.cache_clear()

    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    with open(real_config / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    for name in disable:
        if name in cfg.get("agents", {}):
            cfg["agents"][name]["enabled"] = False
    with open(config_dir / "config.yaml", "w") as f:
        yaml.dump(cfg, f)

    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=config_dir,
    )
