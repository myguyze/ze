from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

import pytest

from ze_core.errors import UnknownDialError, UnknownProfileError
from ze_personal.persona.postgres import PostgresPersonaStore
from ze_personal.persona.types import PersonaState


_PROFILES = {
    "default": {
        "traits": ["direct", "warm"],
        "verbosity": "concise",
        "custom_instructions": "",
        "dials": {"humor": 0.5, "directness": 0.7},
    },
    "formal": {
        "traits": ["professional"],
        "verbosity": "detailed",
        "custom_instructions": "Use formal language.",
        "dials": {"humor": 0.1, "formality": 0.9},
    },
}


def _make_pool(row=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


@pytest.fixture
def store_with_row():
    def _make(profile="default", dials=None, updated_at=None):
        row = {"profile": profile, "dials": dials or {}, "updated_at": updated_at}
        pool, conn = _make_pool(row)
        return PostgresPersonaStore(pool=pool, profiles=_PROFILES), conn
    return _make


async def test_get_state_returns_persisted(store_with_row):
    store, _ = store_with_row(profile="formal", dials={"humor": 0.2})
    state = await store.get_state()
    assert state.profile == "formal"
    assert state.dials == {"humor": 0.2}


async def test_get_state_returns_default_when_no_row():
    pool, conn = _make_pool(row=None)
    conn.fetchrow = AsyncMock(return_value=None)
    store = PostgresPersonaStore(pool=pool, profiles=_PROFILES)
    state = await store.get_state()
    assert state.profile == "default"


async def test_get_active_merges_dial_overrides(store_with_row):
    store, _ = store_with_row(profile="default", dials={"humor": 0.9})
    active = await store.get_active()
    assert active["dials"]["humor"] == 0.9
    assert active["dials"]["directness"] == 0.7  # from profile


async def test_get_active_no_overrides_returns_profile(store_with_row):
    store, _ = store_with_row(profile="default", dials={})
    active = await store.get_active()
    assert active["dials"] == {"humor": 0.5, "directness": 0.7}


async def test_set_profile_valid(store_with_row):
    store, conn = store_with_row()
    await store.set_profile("formal")
    conn.execute.assert_called_once()
    assert "formal" in conn.execute.call_args.args[1]


async def test_set_profile_unknown_raises(store_with_row):
    store, _ = store_with_row()
    with pytest.raises(UnknownProfileError):
        await store.set_profile("nonexistent")


async def test_set_dial_valid(store_with_row):
    store, conn = store_with_row()
    await store.set_dial("humor", 0.8)
    conn.execute.assert_called_once()


async def test_set_dial_unknown_raises(store_with_row):
    store, _ = store_with_row()
    with pytest.raises(UnknownDialError):
        await store.set_dial("nonexistent_dial", 0.5)


async def test_set_dial_out_of_range_raises(store_with_row):
    store, _ = store_with_row()
    with pytest.raises(ValueError):
        await store.set_dial("humor", 1.5)


async def test_reset_dials(store_with_row):
    store, conn = store_with_row(dials={"humor": 0.9})
    await store.reset_dials()
    conn.execute.assert_called_once()


async def test_available_profiles(store_with_row):
    store, _ = store_with_row()
    profiles = store.available_profiles()
    assert set(profiles) == {"default", "formal"}
