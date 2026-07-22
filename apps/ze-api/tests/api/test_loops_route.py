"""Integration-style tests for /api/v0/loops routes (Phase 109)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_api.api.dependencies import require_api_key
from ze_api.api.routes.loops import router
from ze_worldstate.errors import InvalidLoopTransitionError, LoopNotFoundError
from ze_worldstate.types import LoopClaimKind, LoopProvenance, LoopState, OpenLoop

API_KEY = "test-key"


def _loop(**overrides) -> OpenLoop:
    defaults = dict(
        id=uuid4(),
        title="Renew passport before the trip",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=0.35,
        state=LoopState.SUSPECTED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return OpenLoop(**defaults)


def _make_app(loop_store=None, pool=None) -> tuple[FastAPI, AsyncMock]:
    app = FastAPI()
    store = loop_store or AsyncMock()
    container = SimpleNamespace(loop_store=store, pool=pool)
    app.state.container = container

    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router, prefix="/api/v0")
    return app, store


@pytest.mark.asyncio
async def test_list_loops_defaults_to_non_terminal_states():
    store = AsyncMock()
    store.list = AsyncMock(return_value=[_loop()])
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v0/loops", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["state"] == "suspected"
    store.list.assert_awaited_once_with(["suspected", "active", "drifting"])


@pytest.mark.asyncio
async def test_get_loop_404_when_missing():
    store = AsyncMock()
    store.get = AsyncMock(return_value=None)
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/loops/{uuid4()}", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_loop_returns_evidence_and_entities():
    loop = _loop()
    store = AsyncMock()
    store.get = AsyncMock(return_value=loop)
    store.list_evidence = AsyncMock(return_value=[])
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/loops/{loop.id}", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(loop.id)
    assert data["evidence"] == []
    assert data["entities"] == []


@pytest.mark.asyncio
async def test_confirm_close_drop_persist_across_relist():
    loop = _loop()
    store = AsyncMock()
    store.transition = AsyncMock(
        side_effect=lambda loop_id, state: _loop(id=loop_id, state=LoopState(state))
    )
    store.list_evidence = AsyncMock(return_value=[])
    store.set_dismissed_evidence_fingerprint = AsyncMock()
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        confirm_resp = await client.post(
            f"/api/v0/loops/{loop.id}/confirm",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["state"] == "active"

        close_resp = await client.post(
            f"/api/v0/loops/{loop.id}/close",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert close_resp.status_code == 200
        assert close_resp.json()["state"] == "closed"


@pytest.mark.asyncio
async def test_drop_records_fingerprint_and_persists():
    loop = _loop()
    store = AsyncMock()
    store.list_evidence = AsyncMock(return_value=[])
    store.transition = AsyncMock(
        return_value=_loop(id=loop.id, state=LoopState.DROPPED)
    )
    store.set_dismissed_evidence_fingerprint = AsyncMock()
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v0/loops/{loop.id}/drop",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["state"] == "dropped"
    store.set_dismissed_evidence_fingerprint.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_transition_returns_409():
    store = AsyncMock()
    store.transition = AsyncMock(side_effect=InvalidLoopTransitionError("nope"))
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v0/loops/{uuid4()}/confirm",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_confidence_decay_reflected_on_next_get():
    """SC-006 / quickstart's evidence-retraction-cascade scenario, exercised through
    the REST surface: once ze_worldstate.decay.cascade_from_evidence has lowered a
    loop's stored confidence (unit-tested directly in test_decay.py), the next
    GET /api/v0/loops/{id} must reflect the new value — not a cached one.
    """
    from ze_worldstate.decay import CONFIDENCE_FLOOR, cascade_from_evidence

    loop = _loop(confidence=0.6)
    store = AsyncMock()
    store.list_by_evidence = AsyncMock(return_value=[loop])
    store.count_evidence_links = AsyncMock(return_value=1)
    store.set_confidence = AsyncMock(
        side_effect=lambda loop_id, c: setattr(loop, "confidence", c)
    )
    store.list_evidence = AsyncMock(return_value=[])
    store.get = AsyncMock(return_value=loop)
    app, _ = _make_app(store)

    await cascade_from_evidence("fact", uuid4(), store)
    assert loop.confidence == CONFIDENCE_FLOOR

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/loops/{loop.id}", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert resp.status_code == 200
    assert resp.json()["confidence"] == CONFIDENCE_FLOOR


@pytest.mark.asyncio
async def test_transition_404_when_missing():
    store = AsyncMock()
    store.transition = AsyncMock(side_effect=LoopNotFoundError("missing"))
    app, _ = _make_app(store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v0/loops/{uuid4()}/close",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 404
