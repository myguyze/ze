from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ze_api.api import dependencies
from ze_api.api.routes import memory


def make_pool(fetchrow_return=None):
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def make_client(pool):
    app = FastAPI()
    app.include_router(memory.router, prefix="/memory")
    app.dependency_overrides[dependencies.get_pool] = lambda: pool
    return TestClient(app)


def test_api_get_profile_200():
    now = datetime(2026, 5, 20, 2, 0, 0, tzinfo=timezone.utc)
    row = {
        "preferences": "Likes brevity.",
        "habits": "Works mornings.",
        "topics": "AI.",
        "relationships": "Has a cat.",
        "goals": "Ship Ze.",
        "updated_at": now,
        "version": 3,
    }
    client = make_client(make_pool(fetchrow_return=row))
    resp = client.get("/memory/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["preferences"] == "Likes brevity."
    assert data["version"] == 3


def test_api_get_profile_404_when_all_empty():
    row = {
        "preferences": "", "habits": "", "topics": "",
        "relationships": "", "goals": "",
        "updated_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
        "version": 0,
    }
    client = make_client(make_pool(fetchrow_return=row))
    resp = client.get("/memory/profile")
    assert resp.status_code == 404


def test_api_get_profile_404_when_no_row():
    client = make_client(make_pool(fetchrow_return=None))
    resp = client.get("/memory/profile")
    assert resp.status_code == 404
