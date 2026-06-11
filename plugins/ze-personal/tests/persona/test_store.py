from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_personal.persona.postgres import PostgresPersonaStore as PersonaStore
from ze_personal.persona.types import PersonaState
from ze_core.settings import Settings
from ze_core.errors import UnknownDialError, UnknownProfileError


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_conn():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_store(pool=None, settings=None):
    s = settings or make_settings()
    cfg = s.persona_config
    return PersonaStore(
        pool=pool or make_pool(),
        profiles=cfg.get("profiles", {}),
        default_profile=cfg.get("profile", "default"),
    )


def make_row(profile="default", dials=None, updated_at=None):
    return {
        "profile": profile,
        "dials": dials or {},
        "updated_at": updated_at or datetime.now(timezone.utc),
    }


# ── get_active ────────────────────────────────────────────────────────────────

async def test_get_active_returns_default_profile_when_no_overrides():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=make_row("default", dials={}))
    store = make_store(pool=make_pool(conn))

    result = await store.get_active()

    assert result["traits"] == ["direct", "warm", "concise"]
    assert result["verbosity"] == "concise"
    assert "dials" in result
    assert result["dials"]["humor"] == pytest.approx(0.3)


async def test_get_active_merges_dial_overrides():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=make_row("default", dials={"humor": 0.9}))
    store = make_store(pool=make_pool(conn))

    result = await store.get_active()

    # DB override wins over YAML default
    assert result["dials"]["humor"] == pytest.approx(0.9)
    # Other dials come from YAML
    assert result["dials"]["directness"] == pytest.approx(0.9)


async def test_get_active_returns_correct_profile_by_name():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=make_row("stoic", dials={}))
    store = make_store(pool=make_pool(conn))

    result = await store.get_active()

    assert result["traits"] == ["precise", "measured"]
    assert result["dials"]["humor"] == pytest.approx(0.05)


async def test_get_active_falls_back_gracefully_when_db_row_absent():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    store = make_store(pool=make_pool(conn))

    result = await store.get_active()

    assert "traits" in result
    assert "dials" in result


# ── set_profile ───────────────────────────────────────────────────────────────

async def test_set_profile_executes_update():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))

    await store.set_profile("stoic")

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "stoic" in call_args


async def test_set_profile_raises_for_unknown_name():
    store = make_store()

    with pytest.raises(UnknownProfileError, match="Unknown profile"):
        await store.set_profile("nonexistent")


# ── set_dial ─────────────────────────────────────────────────────────────────

async def test_set_dial_executes_update():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))

    await store.set_dial("humor", 0.8)

    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args[0]
    assert "humor" in call_args
    assert 0.8 in call_args


async def test_set_dial_raises_for_unknown_dial():
    store = make_store()

    with pytest.raises(UnknownDialError, match="Unknown dial"):
        await store.set_dial("sarcasm", 0.5)


async def test_set_dial_raises_for_out_of_range_value():
    store = make_store()

    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        await store.set_dial("humor", 1.5)


# ── reset_dials ───────────────────────────────────────────────────────────────

async def test_reset_dials_executes_update():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))

    await store.reset_dials()

    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args[0][0]
    assert "dials = '{}'" in sql


# ── available_profiles ────────────────────────────────────────────────────────

def test_available_profiles_returns_yaml_keys():
    store = make_store()
    profiles = store.available_profiles()

    assert "default" in profiles
    assert "stoic" in profiles
    assert "playful" in profiles
