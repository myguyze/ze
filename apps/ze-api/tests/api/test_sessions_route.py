from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ze_api.api import dependencies
from ze_api.api.routes import sessions as sessions_route
from ze_core.conversation.sessions.types import (
    Session,
    SessionListPage,
    SessionSearchHit,
)


@pytest.fixture
def mock_store():
    now = datetime.now(timezone.utc)
    session = Session(
        id="thread-1",
        title="Calendar help",
        preview="Tomorrow at 3",
        title_source="generated",
        created_at=now,
        last_active_at=now,
    )
    store = MagicMock()
    store.list_page = AsyncMock(
        return_value=SessionListPage(items=[session], next_before=None),
    )
    store.search = AsyncMock(
        return_value=[
            SessionSearchHit(
                session=session,
                match_source="message",
                snippet="your <b>calendar</b>",
                rank=0.8,
            )
        ],
    )
    store.create = AsyncMock(return_value=session)
    return store


@pytest.fixture
def client(mock_store):
    app = FastAPI()
    app.state.container = SimpleNamespace(session_store=mock_store)
    app.include_router(sessions_route.router, prefix="/api/v0")
    app.dependency_overrides[dependencies.require_api_key] = lambda: None

    with TestClient(app) as test_client:
        yield test_client, mock_store


def test_list_sessions_returns_paginated_envelope(client):
    test_client, store = client
    resp = test_client.get("/api/v0/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["title_source"] == "generated"
    assert data["next_before"] is None
    store.list_page.assert_awaited_once()


def test_search_sessions_returns_hits(client):
    test_client, store = client
    resp = test_client.get("/api/v0/sessions/search", params={"q": "calendar"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["match_source"] == "message"
    assert data[0]["snippet"] == "your <b>calendar</b>"
    store.search.assert_awaited_once_with("calendar", limit=20)
