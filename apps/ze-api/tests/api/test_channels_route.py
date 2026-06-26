"""Tests for GET/PATCH /api/v0/channels."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_api.api.routes.channels import router
from ze_api.api.dependencies import require_api_key
from ze_personal.channels.types import UserChannel


API_KEY = "test-key"


def _user_channel(
    channel_id: str = "gmail:alice@example.com",
    poll_enabled: bool = True,
    is_default: bool = False,
) -> UserChannel:
    return UserChannel(
        id=uuid4(),
        channel_id=channel_id,
        channel_type="email",
        handle="alice@example.com",
        display_name="Personal Gmail",
        is_default_outbound=is_default,
        poll_enabled=poll_enabled,
        created_at=datetime.now(timezone.utc),
    )


def _make_app(
    user_channels: list[UserChannel] | None = None,
    watermark=None,
    registry_channel=None,
) -> FastAPI:
    app = FastAPI()

    user_channel_store = AsyncMock()
    user_channel_store.list_all = AsyncMock(return_value=user_channels or [])
    user_channel_store.get = AsyncMock(return_value=(user_channels or [None])[0])
    user_channel_store.set_poll_enabled = AsyncMock()
    user_channel_store.set_default_outbound = AsyncMock()
    user_channel_store.set_display_name = AsyncMock()

    watermark_store = AsyncMock()
    watermark_store.get = AsyncMock(return_value=watermark or datetime.now(timezone.utc))

    channel_registry = MagicMock()
    channel_registry.inbound_channels.return_value = []
    channel_registry.get_inbound_by_id.return_value = registry_channel

    container = SimpleNamespace(
        _plugin_stores={
            "user_channel_store": user_channel_store,
            "watermark_store": watermark_store,
        },
        channel_registry=channel_registry,
        settings=SimpleNamespace(ze_api_key=API_KEY),
    )
    app.state.container = container
    app.state.settings = container.settings

    # Override auth to use test key
    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router)
    return app


# ── GET /api/v0/channels ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_channels_returns_empty_when_no_channels():
    app = _make_app(user_channels=[])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/channels", headers={"Authorization": f"Bearer {API_KEY}"})
    assert resp.status_code == 200
    assert resp.json() == {"channels": []}


@pytest.mark.asyncio
async def test_list_channels_returns_channel_info():
    uc = _user_channel()
    app = _make_app(user_channels=[uc])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/channels", headers={"Authorization": f"Bearer {API_KEY}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["channels"]) == 1
    ch = data["channels"][0]
    assert ch["channel_id"] == uc.channel_id
    assert ch["channel_type"] == "email"
    assert ch["poll_enabled"] is True
    assert ch["supports_push"] is False


# ── PATCH /api/v0/channels/{id} ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_poll_enabled_calls_store():
    uc = _user_channel()
    app = _make_app(user_channels=[uc])
    user_channel_store = app.state.container._plugin_stores["user_channel_store"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v0/channels/{uc.channel_id}",
            json={"poll_enabled": False},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    assert resp.status_code == 200
    user_channel_store.set_poll_enabled.assert_called_once_with(uc.channel_id, False)


@pytest.mark.asyncio
async def test_patch_default_outbound_calls_store():
    uc = _user_channel()
    app = _make_app(user_channels=[uc])
    user_channel_store = app.state.container._plugin_stores["user_channel_store"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v0/channels/{uc.channel_id}",
            json={"is_default_outbound": True},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    assert resp.status_code == 200
    user_channel_store.set_default_outbound.assert_called_once_with(uc.channel_id)


@pytest.mark.asyncio
async def test_patch_unknown_channel_returns_404():
    app = _make_app(user_channels=[])
    app.state.container._plugin_stores["user_channel_store"].get = AsyncMock(return_value=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/v0/channels/nonexistent",
            json={"poll_enabled": True},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
    assert resp.status_code == 404
