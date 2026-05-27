"""Tests for telemetry: CostContext, CostStore, CostTracker, CostReconciler."""
import asyncio
from contextvars import copy_context
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_core.telemetry.context import (
    CostContext,
    get_cost_context,
    set_agent_context,
    set_flow_context,
)
from ze_core.telemetry.postgres import PostgresCostStore
from ze_core.telemetry.reconciler import CostReconciler
from ze_core.telemetry.sqlite import SQLiteCostStore
from ze_core.telemetry.store import CostStore
from ze_core.telemetry.tracker import CostTracker
from ze_core.telemetry.types import CostRecord, UsageInfo


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_pool(rows=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.execute = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn


def _make_rec(**kwargs) -> CostRecord:
    defaults = dict(
        agent="a", flow_type="f", model="m",
        prompt_tokens=1, completion_tokens=2, total_tokens=3,
        duration_ms=100, session_id=None, cost_usd=None, generation_id=None,
    )
    return CostRecord(**{**defaults, **kwargs})


# ── TestCostContext ───────────────────────────────────────────────────────────

class TestCostContext:
    def test_get_returns_default_when_unset(self):
        ctx = get_cost_context()
        assert ctx.flow_type == "unknown"
        assert ctx.agent == "unknown"
        assert ctx.session_id is None

    def test_set_flow_context_creates_entry(self):
        def _run():
            set_flow_context("research", session_id="s1")
            ctx = get_cost_context()
            assert ctx.flow_type == "research"
            assert ctx.session_id == "s1"
            assert ctx.agent == "unknown"
        copy_context().run(_run)

    def test_set_agent_context_updates_agent(self):
        def _run():
            set_flow_context("companion")
            set_agent_context("companion_agent")
            ctx = get_cost_context()
            assert ctx.agent == "companion_agent"
            assert ctx.flow_type == "companion"
        copy_context().run(_run)

    def test_set_agent_context_no_op_when_no_flow(self):
        def _run():
            set_agent_context("orphan")
            ctx = get_cost_context()
            assert ctx.flow_type == "unknown"
            assert ctx.agent == "unknown"
        copy_context().run(_run)

    def test_set_flow_context_preserves_agent(self):
        def _run():
            set_flow_context("flow1")
            set_agent_context("agent1")
            set_flow_context("flow2", session_id="s2")
            ctx = get_cost_context()
            assert ctx.flow_type == "flow2"
            assert ctx.agent == "agent1"
            assert ctx.session_id == "s2"
        copy_context().run(_run)

    def test_context_is_frozen(self):
        ctx = CostContext(flow_type="f", agent="a")
        with pytest.raises(Exception):
            ctx.flow_type = "x"  # type: ignore[misc]

    def test_context_isolation_between_tasks(self):
        results = {}
        def _task_a():
            set_flow_context("flow-a")
            results["a"] = get_cost_context().flow_type
        def _task_b():
            set_flow_context("flow-b")
            results["b"] = get_cost_context().flow_type
        copy_context().run(_task_a)
        copy_context().run(_task_b)
        assert results["a"] == "flow-a"
        assert results["b"] == "flow-b"


# ── TestCostStore (Protocol) ──────────────────────────────────────────────────

class TestCostStoreProtocol:
    def test_postgres_store_satisfies_protocol(self):
        pool, _ = _make_pool()
        store = PostgresCostStore(pool)
        assert isinstance(store, CostStore)

    async def test_sqlite_store_satisfies_protocol(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        assert isinstance(store, CostStore)
        await store.aclose()


# ── TestPostgresCostStore ─────────────────────────────────────────────────────

class TestPostgresCostStore:
    async def test_write_executes_insert(self):
        pool, conn = _make_pool()
        store = PostgresCostStore(pool)
        await store.write(_make_rec())
        conn.execute.assert_awaited_once()
        sql = conn.execute.call_args[0][0]
        assert "INSERT INTO llm_cost_log" in sql

    async def test_write_swallows_db_error(self):
        pool, conn = _make_pool()
        conn.execute = AsyncMock(side_effect=Exception("db down"))
        store = PostgresCostStore(pool)
        await store.write(_make_rec())  # must not raise

    async def test_fetch_pending_returns_rows(self):
        rows = [{"id": "r1", "generation_id": "gen-1"}]
        pool, conn = _make_pool(rows)
        store = PostgresCostStore(pool)
        result = await store.fetch_pending(batch_size=50, min_age_seconds=120)
        assert result == rows

    async def test_update_cost_executes_update(self):
        pool, conn = _make_pool()
        store = PostgresCostStore(pool)
        await store.update_cost("row-1", 0.0042)
        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args[0]
        assert 0.0042 in call_args
        assert "row-1" in call_args


# ── TestSQLiteCostStore ───────────────────────────────────────────────────────

class TestSQLiteCostStore:
    async def test_setup_creates_table(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        async with store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_cost_log'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        await store.aclose()

    async def test_write_stores_record(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        await store.write(_make_rec(model="test-model", total_tokens=42))
        async with store._conn.execute("SELECT COUNT(*) FROM llm_cost_log") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1
        await store.aclose()

    async def test_write_stores_correct_values(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        rec = _make_rec(model="my-model", agent="researcher", total_tokens=99, generation_id="gen-x")
        await store.write(rec)
        async with store._conn.execute("SELECT model, agent, total_tokens, generation_id FROM llm_cost_log") as cur:
            row = await cur.fetchone()
        assert row["model"] == "my-model"
        assert row["agent"] == "researcher"
        assert row["total_tokens"] == 99
        assert row["generation_id"] == "gen-x"
        await store.aclose()

    async def test_aclose_sets_conn_none(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        await store.aclose()
        assert store._conn is None

    async def test_double_close_is_safe(self):
        store = SQLiteCostStore(":memory:")
        await store.setup()
        await store.aclose()
        await store.aclose()  # must not raise

    async def test_write_before_setup_logs_warning(self):
        store = SQLiteCostStore(":memory:")
        await store.write(_make_rec())  # must not raise


# ── TestCostTracker ───────────────────────────────────────────────────────────

class TestCostTracker:
    def test_record_without_store_does_not_raise(self):
        tracker = CostTracker(store=None)
        tracker.record(model="m", prompt_tokens=1, completion_tokens=2, total_tokens=3, duration_ms=50)

    async def test_record_with_store_creates_task(self):
        store = AsyncMock(spec=CostStore)
        tracker = CostTracker(store=store)
        created = []
        with patch("asyncio.create_task", side_effect=lambda coro: created.append(coro) or MagicMock()):
            tracker.record(model="m", prompt_tokens=1, completion_tokens=2, total_tokens=3, duration_ms=50)
        assert len(created) == 1

    async def test_record_calls_store_write(self):
        store = AsyncMock(spec=CostStore)
        tracker = CostTracker(store=store)
        with patch("asyncio.create_task", lambda coro: asyncio.ensure_future(coro)):
            tracker.record(model="m", prompt_tokens=1, completion_tokens=2, total_tokens=3, duration_ms=50)
        await asyncio.sleep(0)
        store.write.assert_awaited_once()
        rec = store.write.call_args[0][0]
        assert rec.model == "m"
        assert rec.total_tokens == 3

    async def test_record_captures_cost_context(self):
        store = AsyncMock(spec=CostStore)
        tracker = CostTracker(store=store)
        set_flow_context("research", session_id="sess-1")
        set_agent_context("researcher")
        with patch("asyncio.create_task", lambda coro: asyncio.ensure_future(coro)):
            tracker.record("m", 1, 2, 3, 10)
        await asyncio.sleep(0)
        rec = store.write.call_args[0][0]
        assert rec.flow_type == "research"
        assert rec.agent == "researcher"
        assert rec.session_id == "sess-1"

    def test_record_audio_seconds(self):
        tracker = CostTracker(store=None)
        tracker.record(model="whisper", prompt_tokens=0, completion_tokens=0,
                       total_tokens=0, duration_ms=200, audio_seconds=12.5)


# ── TestCostReconciler ────────────────────────────────────────────────────────

class TestCostReconciler:
    async def test_no_rows_returns_early(self):
        store = AsyncMock(spec=PostgresCostStore)
        store.fetch_pending = AsyncMock(return_value=[])
        client = AsyncMock()
        reconciler = CostReconciler(store=store, openrouter_client=client)
        await reconciler.run()
        client.fetch_generation_cost.assert_not_awaited()

    async def test_fetches_cost_and_updates_row(self):
        row = {"id": "row-1", "generation_id": "gen-abc"}
        store = AsyncMock(spec=PostgresCostStore)
        store.fetch_pending = AsyncMock(return_value=[row])
        store.update_cost = AsyncMock()
        client = AsyncMock()
        client.fetch_generation_cost = AsyncMock(return_value=0.0042)
        reconciler = CostReconciler(store=store, openrouter_client=client)
        await reconciler.run()
        client.fetch_generation_cost.assert_awaited_once_with("gen-abc")
        store.update_cost.assert_awaited_once_with("row-1", 0.0042)

    async def test_skips_row_when_cost_unavailable(self):
        row = {"id": "row-2", "generation_id": "gen-xyz"}
        store = AsyncMock(spec=PostgresCostStore)
        store.fetch_pending = AsyncMock(return_value=[row])
        store.update_cost = AsyncMock()
        client = AsyncMock()
        client.fetch_generation_cost = AsyncMock(return_value=None)
        reconciler = CostReconciler(store=store, openrouter_client=client)
        await reconciler.run()
        store.update_cost.assert_not_awaited()

    async def test_processes_multiple_rows(self):
        rows = [{"id": f"r{i}", "generation_id": f"gen-{i}"} for i in range(3)]
        store = AsyncMock(spec=PostgresCostStore)
        store.fetch_pending = AsyncMock(return_value=rows)
        store.update_cost = AsyncMock()
        client = AsyncMock()
        client.fetch_generation_cost = AsyncMock(return_value=0.001)
        reconciler = CostReconciler(store=store, openrouter_client=client)
        await reconciler.run()
        assert client.fetch_generation_cost.await_count == 3
        assert store.update_cost.await_count == 3


# ── TestUsageInfo ─────────────────────────────────────────────────────────────

class TestUsageInfo:
    def test_fields(self):
        u = UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30,
                      generation_id="gen-1", duration_ms=150)
        assert u.total_tokens == 30
        assert u.generation_id == "gen-1"
