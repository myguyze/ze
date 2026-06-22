from __future__ import annotations

import asyncpg
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ze_agents.client import LLMClient
from ze_agents.hooks import register_hook
from ze_logging import get_logger
from ze_agents.settings import Settings as CoreSettings
from ze_agents.tool_cap_hook import ToolCallCapHook
from ze_components.hook import ComponentCollectionHook
from ze_core.capability.gate import CapabilityGate
from ze_core.capability.overrides import PostgresCapabilityOverrideStore
from ze_core.checkpoint_serde import build_checkpoint_serde
from ze_core.embeddings import get_embedder
from ze_core.openrouter.client import OpenRouterClient
from ze_core.routing.complexity import ComplexityEstimator
from ze_core.routing.router import EmbeddingRouter
from ze_core.routing.store import PostgresRoutingStore
from ze_core.routing.types import RouterConfig
from ze_core.telemetry.postgres import PostgresCostStore
from ze_core.telemetry.reconciler import CostReconciler
from ze_core.telemetry.tracker import CostTracker
from ze_data.domain import DataDomain
from ze_data.portability.assembler import bulk_insert
from ze_memory.consolidator import MemoryConsolidator
from ze_memory.graph import PostgresGraphStore
from ze_memory.retriever import PostgresMemoryStore
from ze_memory.session_summary import SessionSummariser

log = get_logger(__name__)


@dataclass
class EngineStack:
    pool: asyncpg.Pool
    checkpointer_pool: Any
    embedder: Any
    openrouter_client: OpenRouterClient
    cost_store: PostgresCostStore
    cost_tracker: CostTracker
    memory_store: PostgresMemoryStore
    memory_consolidator: MemoryConsolidator
    session_summariser: SessionSummariser
    capability_gate: CapabilityGate
    estimator: ComplexityEstimator
    core_settings: CoreSettings
    dep_map: dict[type, Any] = field(default_factory=dict)


async def build_engine_stack(
    pool: asyncpg.Pool,
    checkpointer_pool: Any,
    settings: Any,
) -> EngineStack:
    embedder = get_embedder()
    core_settings = settings.to_core_settings()

    cost_store = PostgresCostStore(pool=pool)
    cost_tracker = CostTracker(store=cost_store)

    openrouter_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        logger=get_logger("ze.openrouter"),
        http_referer=settings.openrouter_http_referer,
        title=settings.openrouter_title,
        cost_tracker=cost_tracker,
    )

    graph_store = PostgresGraphStore(pool=pool)
    memory_store = PostgresMemoryStore(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
        graph_store=graph_store,
    )

    memory_consolidator = MemoryConsolidator(
        store=memory_store,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    session_summariser = SessionSummariser(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    estimator = ComplexityEstimator()
    override_store = PostgresCapabilityOverrideStore(pool=pool)
    capability_gate = CapabilityGate(override_store=override_store)
    await capability_gate.load_persistent_overrides()

    dep_map: dict[type, Any] = {
        asyncpg.Pool: pool,
        OpenRouterClient: openrouter_client,
        LLMClient: openrouter_client,
        PostgresMemoryStore: memory_store,
    }

    return EngineStack(
        pool=pool,
        checkpointer_pool=checkpointer_pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        cost_store=cost_store,
        cost_tracker=cost_tracker,
        memory_store=memory_store,
        memory_consolidator=memory_consolidator,
        session_summariser=session_summariser,
        capability_gate=capability_gate,
        estimator=estimator,
        core_settings=core_settings,
        dep_map=dep_map,
    )


async def build_checkpointer(
    checkpointer_pool: Any,
    plugins: list,
) -> AsyncPostgresSaver:
    checkpointer = AsyncPostgresSaver(
        checkpointer_pool,
        serde=build_checkpoint_serde(plugins),
    )
    await checkpointer.setup()
    return checkpointer


def build_router(stack: EngineStack) -> EmbeddingRouter:
    return EmbeddingRouter(
        embedder=stack.embedder,
        openrouter_client=stack.openrouter_client,
        routing_store=PostgresRoutingStore(stack.pool),
        config=RouterConfig(),
        estimator=stack.estimator,
    )


def register_harness_hooks(settings: Any) -> ComponentCollectionHook:
    component_hook = ComponentCollectionHook()
    register_hook(component_hook)
    log.info("component_collection_hook_registered")

    register_hook(ToolCallCapHook(max_tool_calls=settings.max_tool_calls_per_turn))
    log.info("tool_call_cap_hook_registered", max_tool_calls=settings.max_tool_calls_per_turn)
    return component_hook


def engine_data_domains(pool: asyncpg.Pool) -> list[DataDomain]:
    def _mk_export(tbl: str):
        async def _export(p) -> list[dict]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT * FROM {tbl}")
                return [dict(r) for r in rows]

        return _export

    def _mk_delete(*tables: str):
        async def _delete(p) -> None:
            async with pool.acquire() as conn:
                for tbl in tables:
                    await conn.execute(f"DELETE FROM {tbl}")

        return _delete

    def _mk_import(tbl: str):
        async def _import(conn, rows: list[dict]) -> int:
            return await bulk_insert(conn, tbl, rows)

        return _import

    async def _export_checkpoints(p) -> list[dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM checkpoints")
            return [dict(r) for r in rows]

    async def _delete_checkpoints(p) -> None:
        async with pool.acquire() as conn:
            for tbl in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await conn.execute(f"DELETE FROM {tbl}")

    def _engine_domain(name: str, tbl: str) -> DataDomain:
        return DataDomain(
            name,
            _mk_export(tbl),
            _mk_delete(tbl),
            delete_order=10,
            importer=_mk_import(tbl),
        )

    return [
        _engine_domain("telemetry.costs", "llm_cost_log"),
        _engine_domain("telemetry.capabilities", "capability_overrides"),
        _engine_domain("routing.log", "routing_log"),
        _engine_domain("messages.store", "messages"),
        _engine_domain("confirmations", "pending_confirmations"),
        _engine_domain("proactive.log", "push_log"),
        _engine_domain("sessions", "sessions"),
        DataDomain(
            "onboarding",
            _mk_export("onboarding_sessions"),
            _mk_delete("onboarding_steps", "onboarding_sessions", "onboarding_seeds"),
            delete_order=10,
            importer=_mk_import("onboarding_sessions"),
        ),
        DataDomain("graph.checkpoints", _export_checkpoints, _delete_checkpoints, delete_order=50),
    ]


def register_engine_jobs(
    workflow_scheduler: Any,
    _settings: Any,
    stack: EngineStack,
) -> None:
    cost_reconciler = CostReconciler(
        store=stack.cost_store,
        openrouter_client=stack.openrouter_client,
    )
    workflow_scheduler.schedule_job(
        fn=cost_reconciler.run,
        cron="*/15 * * * *",
        job_id="cost_reconciliation",
    )
    log.info("cost_reconciliation_scheduled")
