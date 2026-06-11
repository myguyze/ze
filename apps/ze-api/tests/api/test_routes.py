import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ze_api.api import dependencies
from ze_api.api.routes import capabilities, memory, routing
from ze_api.testing import make_gate
from ze_api.logging import configure_logging
from ze_api.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


def make_settings(config_dir):
    get_settings.cache_clear()
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=config_dir,
    )


@pytest.fixture
def capabilities_yaml(tmp_path):
    cfg = {
        "agents": {
            "research": {"enabled": True, "capabilities": {"read": "autonomous"}},
            "companion": {"enabled": True, "capabilities": {"reason": "autonomous"}},
        }
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg))
    return path


@pytest.fixture
def gate(capabilities_yaml):
    cfg = yaml.safe_load(capabilities_yaml.read_text())
    store = MagicMock()
    store.get_all = AsyncMock(return_value={})
    store.set = AsyncMock()
    gate = make_gate(cfg["agents"], override_store=store)
    gate._persistent_cache = {}
    yield gate
    gate._restore_registry()


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def client(gate, mock_pool, capabilities_yaml):
    pool, conn = mock_pool
    settings = make_settings(capabilities_yaml.parent)

    app = FastAPI()
    app.include_router(capabilities.router, prefix="/capabilities")
    app.include_router(memory.router, prefix="/memory")
    app.include_router(routing.router, prefix="/routing")

    app.dependency_overrides[dependencies.get_capability_gate] = lambda: gate
    app.dependency_overrides[dependencies.get_pool] = lambda: pool
    app.dependency_overrides[dependencies.get_settings] = lambda: settings

    with TestClient(app) as c:
        yield c, conn


# ── GET /capabilities ─────────────────────────────────────────────────────────

def test_get_capabilities_returns_config(client):
    c, _ = client
    resp = c.get("/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "research" in data
    assert data["research"]["read"] == "autonomous"


# ── PUT /capabilities/{agent}/{intent} ────────────────────────────────────────

def test_put_capability_updates_mode(client, gate):
    c, _ = client
    resp = c.put("/capabilities/research/read", json={"mode": "confirm"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["research"]["read"] == "confirm"
    from ze_core.capability.types import GateDecision
    assert gate.evaluate("research", "read", {}) == GateDecision.AWAIT_CONFIRMATION


def test_put_capability_unknown_agent_returns_422(client):
    c, _ = client
    resp = c.put("/capabilities/ghost/read", json={"mode": "confirm"})
    assert resp.status_code == 422


def test_put_capability_unknown_intent_returns_422(client):
    c, _ = client
    resp = c.put("/capabilities/research/delete", json={"mode": "confirm"})
    assert resp.status_code == 422


def test_put_capability_invalid_mode_returns_422(client):
    c, _ = client
    resp = c.put("/capabilities/research/read", json={"mode": "full_send"})
    assert resp.status_code == 422


# ── GET /routing/log ──────────────────────────────────────────────────────────

def test_get_routing_log_returns_list(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    resp = c.get("/routing/log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_routing_log_respects_limit(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    resp = c.get("/routing/log?limit=10&offset=5")
    assert resp.status_code == 200


def test_get_routing_log_invalid_limit(client):
    c, _ = client
    resp = c.get("/routing/log?limit=0")
    assert resp.status_code == 422


# ── GET /memory/digest ────────────────────────────────────────────────────────

def test_memory_digest_returns_structure(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    resp = c.get("/memory/digest")
    assert resp.status_code == 200
    data = resp.json()
    assert "unreviewed_facts" in data
    assert "contradicted_facts" in data
    assert "recent_episodes" in data


# ── GET /memory/facts ─────────────────────────────────────────────────────────

def test_memory_facts_returns_list(client):
    c, conn = client
    conn.fetch = AsyncMock(return_value=[])
    resp = c.get("/memory/facts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── OpenAPI schema ────────────────────────────────────────────────────────────

def test_openapi_includes_rest_paths(client):
    c, _ = client
    schema = c.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/capabilities" in paths
    assert "/capabilities/{agent}/{intent}" in paths
    assert "/memory/facts" in paths
    assert "/memory/facts/review" in paths
    assert "/memory/digest" in paths
    assert "/routing/log" in paths


def test_openapi_capabilities_get_has_response_schema(client):
    c, _ = client
    schema = c.get("/openapi.json").json()
    get_op = schema["paths"]["/capabilities"]["get"]
    assert "200" in get_op["responses"]
    assert get_op["summary"]
    assert get_op["description"]
