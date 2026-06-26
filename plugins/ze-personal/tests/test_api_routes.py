from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_personal.api.routes import router
from ze_plugin.api_auth import require_api_key

API_KEY = "test-key"


def _make_app(store=None) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        _plugin_stores={"person_store": store} if store is not None else {},
        settings=SimpleNamespace(ze_api_key=API_KEY),
    )
    app.state.settings = app.state.container.settings
    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_get_contacts_page_returns_tree():
    store = AsyncMock()
    store.list_confirmed = AsyncMock(return_value=[])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/contacts/page", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "People"
    assert isinstance(data["tree"], list)
    store.list_confirmed.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_contacts_page_title_with_count():
    person = SimpleNamespace(
        id=uuid4(),
        name="Maria",
        contact_info={"email": "maria@example.com"},
        notes="Met at conference",
    )
    store = AsyncMock()
    store.list_confirmed = AsyncMock(return_value=[person])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/contacts/page", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    assert resp.json()["title"] == "1 person"


@pytest.mark.asyncio
async def test_list_contacts_returns_empty_without_store():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/contacts", headers={"Authorization": f"Bearer {API_KEY}"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_contacts_returns_confirmed_people():
    person_id = uuid4()
    person = SimpleNamespace(
        id=person_id,
        name="Maria",
        contact_info={"email": "maria@example.com"},
        notes="Met at conference",
    )
    store = AsyncMock()
    store.list_confirmed = AsyncMock(return_value=[person])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/contacts", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Maria"
    assert data[0]["email"] == "maria@example.com"
