"""Tests for CapabilityGate persistent overrides and PostgresCapabilityOverrideStore."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.capability import (
    CapabilityGate,
    GateDecision,
    Mode,
    PostgresCapabilityOverrideStore,
)
from ze_core.orchestration import agent, clear_registry
from ze_core.orchestration.types import AgentContext, AgentResult


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


def _register(name: str, capabilities: dict, enabled: bool = True) -> None:
    class _A:
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response="")

    _A.__name__ = f"Agent_{name}"
    _A.name = name
    _A.description = f"Agent {name}"
    _A.enabled = enabled
    _A.capabilities = capabilities
    agent(_A)


def _make_pool(rows=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


# ── PostgresCapabilityOverrideStore ──────────────────────────────────────────

class TestPostgresCapabilityOverrideStore:
    async def test_get_returns_none_when_no_row(self):
        pool, conn = _make_pool()
        store = PostgresCapabilityOverrideStore(pool)
        result = await store.get("calendar", "create")
        assert result is None

    async def test_get_returns_mode_from_row(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"mode": "autonomous"})
        store = PostgresCapabilityOverrideStore(pool)
        result = await store.get("calendar", "create")
        assert result == Mode.AUTONOMOUS

    async def test_set_issues_upsert(self):
        pool, conn = _make_pool()
        store = PostgresCapabilityOverrideStore(pool)
        await store.set("calendar", "create", Mode.AUTONOMOUS)
        conn.execute.assert_awaited_once()
        sql = conn.execute.call_args.args[0]
        assert "INSERT" in sql and "ON CONFLICT" in sql

    async def test_clear_deletes_row(self):
        pool, conn = _make_pool()
        store = PostgresCapabilityOverrideStore(pool)
        await store.clear("calendar", "create")
        conn.execute.assert_awaited_once()

    async def test_get_all_returns_parsed_modes(self):
        rows = [
            {"agent": "calendar", "intent": "create", "mode": "confirm"},
            {"agent": "email", "intent": "read", "mode": "autonomous"},
        ]
        pool, conn = _make_pool(rows)
        conn.fetch = AsyncMock(return_value=rows)
        store = PostgresCapabilityOverrideStore(pool)
        result = await store.get_all()
        assert result == {
            ("calendar", "create"): Mode.CONFIRM,
            ("email", "read"): Mode.AUTONOMOUS,
        }

    async def test_get_all_skips_invalid_modes(self):
        rows = [{"agent": "x", "intent": "y", "mode": "bogus"}]
        pool, conn = _make_pool(rows)
        conn.fetch = AsyncMock(return_value=rows)
        store = PostgresCapabilityOverrideStore(pool)
        result = await store.get_all()
        assert result == {}


# ── CapabilityGate with persistent overrides ─────────────────────────────────

class TestPersistentOverrides:
    async def test_persistent_override_takes_precedence_over_class_attribute(self):
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(
            return_value={("email", "create"): Mode.CONFIRM}
        )
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        assert gate.evaluate("email", "create", {}) == GateDecision.AWAIT_CONFIRMATION

    async def test_no_override_falls_back_to_class_attribute(self):
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(return_value={})
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        assert gate.evaluate("email", "create", {}) == GateDecision.DRAFT

    async def test_set_permanent_updates_cache(self):
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(return_value={})
        override_store.set = AsyncMock()
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        assert gate.evaluate("email", "create", {}) == GateDecision.DRAFT

        await gate.set_permanent("email", "create", Mode.CONFIRM)
        assert gate.evaluate("email", "create", {}) == GateDecision.AWAIT_CONFIRMATION
        override_store.set.assert_awaited_once()

    async def test_clear_permanent_reverts_to_class_attribute(self):
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(
            return_value={("email", "create"): Mode.CONFIRM}
        )
        override_store.clear = AsyncMock()
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        assert gate.evaluate("email", "create", {}) == GateDecision.AWAIT_CONFIRMATION

        await gate.clear_permanent("email", "create")
        assert gate.evaluate("email", "create", {}) == GateDecision.DRAFT

    async def test_persistent_override_can_escalate_beyond_class_ceiling(self):
        # Persistent overrides are treated as a code change — no ceiling.
        # draft_only → autonomous is allowed via persistent override.
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(
            return_value={("email", "create"): Mode.AUTONOMOUS}
        )
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        assert gate.evaluate("email", "create", {}) == GateDecision.EXECUTE

    async def test_session_override_ceiling_derived_from_effective_mode(self):
        # When persistent override raises the base to CONFIRM, the session ceiling
        # is EXECUTE (CONFIRM's ceiling), so a session override to AUTONOMOUS is allowed.
        _register("email", {"create": Mode.DRAFT_ONLY})
        override_store = AsyncMock()
        override_store.get_all = AsyncMock(
            return_value={("email", "create"): Mode.CONFIRM}
        )
        gate = CapabilityGate(override_store=override_store)
        await gate.load_persistent_overrides()
        # Effective mode is CONFIRM, ceiling is EXECUTE — session override to AUTONOMOUS ok
        assert gate.evaluate("email", "create", {"email.create": "autonomous"}) == GateDecision.EXECUTE

    async def test_no_override_store_works_without_load(self):
        _register("cal", {"read": Mode.AUTONOMOUS})
        gate = CapabilityGate()
        # No override store, no load_persistent_overrides call — still works
        assert gate.evaluate("cal", "read", {}) == GateDecision.EXECUTE

    async def test_set_permanent_raises_without_store(self):
        gate = CapabilityGate()
        with pytest.raises(RuntimeError):
            await gate.set_permanent("cal", "read", Mode.CONFIRM)
