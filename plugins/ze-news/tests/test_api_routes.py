from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_news.api.routes import router
from ze_plugin.api_auth import require_api_key

API_KEY = "test-key"


def _make_app(store=None) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        _plugin_stores={"news_store": store} if store is not None else {},
        settings=SimpleNamespace(ze_api_key=API_KEY),
    )
    app.state.settings = app.state.container.settings
    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_get_news_page_returns_tree():
    store = AsyncMock()
    store.get_recent = AsyncMock(return_value=[])
    app = _make_app(store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/news/page", headers={"Authorization": f"Bearer {API_KEY}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "News"
    assert isinstance(data["tree"], list)
    store.get_recent.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_news_returns_empty_without_store():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/news", headers={"Authorization": f"Bearer {API_KEY}"})
    assert resp.status_code == 200
    assert resp.json() == []
