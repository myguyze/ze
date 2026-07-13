"""Tests for GET /api/v0/ui/manifest."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_api.api.dependencies import require_api_key
from ze_api.api.routes.ui import router
from ze_plugin.ui import UiContribution, UiManifest

API_KEY = "test-key"


def _manifest(
    *,
    nav: list[UiContribution] | None = None,
    settings: list[UiContribution] | None = None,
) -> UiManifest:
    return UiManifest(
        nav=tuple(nav or []),
        settings_sections=tuple(settings or []),
    )


def _make_app(manifest: UiManifest | None = None) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        ui_manifest=manifest or _manifest(),
        settings=SimpleNamespace(ze_api_key=API_KEY),
    )
    app.state.settings = app.state.container.settings
    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_get_ui_manifest_returns_empty_lists():
    app = _make_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v0/ui/manifest", headers={"Authorization": f"Bearer {API_KEY}"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"nav": [], "settings_sections": []}


@pytest.mark.asyncio
async def test_get_ui_manifest_returns_plugin_contributions():
    manifest = _manifest(
        nav=[
            UiContribution(
                id="ze_finance.overview",
                plugin="ze_finance",
                kind="nav",
                label="Finance",
                icon="landmark",
                path="finance",
                page_operation_id="getFinancePage",
                priority=50,
            )
        ],
        settings=[
            UiContribution(
                id="ze_finance.settings",
                plugin="ze_finance",
                kind="settings_section",
                label="Finance",
                icon="landmark",
                settings_operation_id="getFinanceSettings",
            )
        ],
    )
    app = _make_app(manifest)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v0/ui/manifest", headers={"Authorization": f"Bearer {API_KEY}"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["nav"][0]["path"] == "finance"
    assert data["nav"][0]["page_operation_id"] == "getFinancePage"
    assert data["settings_sections"][0]["settings_operation_id"] == "getFinanceSettings"
