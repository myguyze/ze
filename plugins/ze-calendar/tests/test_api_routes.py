from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_calendar.api.routes import router
from ze_plugin.api_auth import require_api_key

API_KEY = "test-key"

_PRIMITIVE_TYPE_NAMES = frozenset(
    {"col", "row", "text", "badge", "divider", "spacer", "button", "progress", "table", "form", "connections"}
)


def _assert_valid_tree(nodes: list) -> None:
    """Recursively verify every node carries a known primitive type."""
    for node in nodes:
        assert isinstance(node, dict), f"tree node must be a dict, got {type(node)}"
        assert "type" in node, f"tree node missing 'type': {node}"
        assert node["type"] in _PRIMITIVE_TYPE_NAMES, f"unknown primitive type {node['type']!r}"
        for child_key in ("children", "fields", "connections"):
            if child_key in node and isinstance(node[child_key], list):
                _assert_valid_tree(node[child_key])


def _make_app(store=None) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        _plugin_stores={"reminder_store": store} if store is not None else {},
        settings=SimpleNamespace(ze_api_key=API_KEY),
    )
    app.state.settings = app.state.container.settings
    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_get_reminders_page_returns_tree():
    store = AsyncMock()
    store.list_all = AsyncMock(return_value=[])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/reminders/page", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Upcoming"
    assert isinstance(data["tree"], list)
    _assert_valid_tree(data["tree"])
    store.list_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_reminders_returns_empty_without_store():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/reminders", headers={"Authorization": f"Bearer {API_KEY}"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_reminders_returns_items():
    reminder_id = uuid4()
    reminder = SimpleNamespace(
        id=reminder_id,
        label="Call João",
        fire_at=datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc),
        sent=False,
    )
    store = AsyncMock()
    store.list_all = AsyncMock(return_value=[reminder])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/reminders", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["label"] == "Call João"
    assert data[0]["fired"] is False
