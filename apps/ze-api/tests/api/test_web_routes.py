from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ze_api.api import dependencies
from ze_api.api.routes import contacts, costs, goals, reminders


@pytest.fixture
def container():
    goal = SimpleNamespace(
        id=uuid4(),
        objective="Launch product",
        status=SimpleNamespace(value="active"),
        created_at="2026-06-01T00:00:00+00:00",
    )
    reminder = SimpleNamespace(
        id=uuid4(),
        label="Call João",
        fire_at="2026-06-15T09:00:00+00:00",
        sent=False,
    )
    person = SimpleNamespace(
        id=uuid4(),
        name="Maria",
        contact_info={"email": "maria@example.com"},
        notes="Met at conference",
    )

    goal_store = AsyncMock()
    goal_store.list_active = AsyncMock(return_value=[goal])

    reminder_store = AsyncMock()
    reminder_store.list_all = AsyncMock(return_value=[reminder])

    person_store = AsyncMock()
    person_store.list_confirmed = AsyncMock(return_value=[person])

    return SimpleNamespace(
        _plugin_stores={
            "goal_store": goal_store,
            "reminder_store": reminder_store,
            "person_store": person_store,
        },
    )


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def client(container, mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"total_tokens": 0, "total_cost_usd": 0, "total_calls": 0})

    app = FastAPI()
    app.state.container = container
    app.state.pool = pool
    app.include_router(goals.router, prefix="/api/v0")
    app.include_router(reminders.router, prefix="/api/v0")
    app.include_router(contacts.router, prefix="/api/v0")
    app.include_router(costs.router, prefix="/api/v0/costs")

    app.dependency_overrides[dependencies.get_pool] = lambda: pool
    app.dependency_overrides[dependencies.require_api_key] = lambda: None

    with TestClient(app) as c:
        yield c


def test_list_goals(client):
    resp = client.get("/api/v0/goals")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["objective"] == "Launch product"
    assert data[0]["status"] == "active"


def test_list_reminders(client):
    resp = client.get("/api/v0/reminders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["label"] == "Call João"
    assert data[0]["fired"] is False


def test_list_contacts(client):
    resp = client.get("/api/v0/contacts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Maria"
    assert data[0]["email"] == "maria@example.com"


def test_web_cost_summary(client):
    resp = client.get("/api/v0/costs/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_usd"] == 0
    assert data["total_tokens"] == 0
    assert data["total_calls"] == 0
    assert data["period"] == "Last 30 days"
    assert data["by_agent"] == {}
