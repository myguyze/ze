from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from ze_logging import get_logger
from ze_agents.registry import get_agent as _get_agent
from ze_automation.accountability.store import AccountabilityStore
from ze_automation.goals.executor import GoalExecutor
from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.postgres import PostgresGoalStore
from ze_automation.goals.suggestion_store import GoalSuggestionStore
from ze_automation.jobs.accountability import AccountabilityJob
from ze_automation.jobs.cost_anomaly import CostAnomalyJob
from ze_automation.jobs.goal_narrative import GoalNarrativeJob
from ze_automation.jobs.goal_suggestion import GoalSuggestionJob
from ze_automation.jobs.stuck_goals import StuckGoalJob
from ze_automation.workflow.planner import WorkflowPlanner
from ze_automation.workflow.postgres import PostgresWorkflowStore
from ze_automation.workflow.scheduler import WorkflowScheduler
from ze_automation.workflow.store import WorkflowStore
from ze_data.domain import DataDomain
from ze_data.portability.assembler import bulk_insert
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler

log = get_logger(__name__)


def scheduler_enabled(settings: Any) -> bool:
    cfg = getattr(settings, "config", None) or {}
    wf = cfg.get("workflows", {})
    if "scheduler_enabled" in wf:
        return bool(wf["scheduler_enabled"])
    return os.environ.get("SCHEDULER_ENABLED", "true").lower() != "false"


_AGENT_MODULE_PATHS = [
    "ze_automation.agents.goals.tools",
    "ze_automation.agents.goals.agent",
    "ze_automation.agents.workflow.tools",
    "ze_automation.agents.workflow.agent",
]


@dataclass
class AutomationStack:
    goal_store: PostgresGoalStore
    goal_suggestion_store: GoalSuggestionStore
    goal_planner: GoalPlanner
    goal_executor: GoalExecutor
    workflow_store: PostgresWorkflowStore
    workflow_planner: WorkflowPlanner
    workflow_scheduler: WorkflowScheduler
    accountability_store: AccountabilityStore
    deps: dict[type, Any] = field(default_factory=dict)


def agent_module_paths() -> list[str]:
    return list(_AGENT_MODULE_PATHS)


def import_agent_modules() -> None:
    import importlib

    for module_path in _AGENT_MODULE_PATHS:
        importlib.import_module(module_path)


def automation_data_domains(pool: asyncpg.Pool) -> list[DataDomain]:
    def _export(tbl: str):
        async def _fn(p) -> list[dict]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT * FROM {tbl}")
                return [dict(r) for r in rows]

        return _fn

    def _delete(*tables: str):
        async def _fn(p) -> None:
            async with pool.acquire() as conn:
                for tbl in tables:
                    await conn.execute(f"DELETE FROM {tbl}")

        return _fn

    def _import(tbl: str):
        async def _fn(conn, rows: list[dict]) -> int:
            return await bulk_insert(conn, tbl, rows)

        return _fn

    def _count(tbl: str):
        async def _fn(p) -> int:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(f"SELECT COUNT(*) AS n FROM {tbl}")
                return row["n"]

        return _fn

    def _size(tbl: str):
        async def _fn(p) -> int:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT pg_total_relation_size($1::regclass) AS n", tbl
                )
                return row["n"]

        return _fn

    def _domain(name: str, tbl: str) -> DataDomain:
        return DataDomain(
            name,
            _export(tbl),
            _delete(tbl),
            delete_order=10,
            importer=_import(tbl),
            count=_count(tbl),
            size_bytes=_size(tbl),
        )

    return [
        _domain("automation.goals", "goals"),
        _domain("automation.workflows", "workflows"),
        _domain("automation.accountability", "accountability_anomalies"),
    ]


def build_automation_stack(shared: Any, settings: Any) -> AutomationStack:
    pool = shared.pool
    openrouter_client = shared.openrouter_client
    memory_store = shared.memory_store

    workflow_store = PostgresWorkflowStore(db_pool=pool)
    workflow_scheduler = WorkflowScheduler(
        workflow_store=workflow_store,
        enabled=scheduler_enabled(settings),
    )

    goal_store = PostgresGoalStore(pool=pool)
    goal_suggestion_store = GoalSuggestionStore(pool=pool)
    goal_planner = GoalPlanner(
        client=openrouter_client,
        memory_store=memory_store,
        embedder=shared.embedder,
    )

    goal_executor = GoalExecutor(
        goal_store=goal_store,
        goal_planner=goal_planner,
        push=lambda _: None,
        agent_getter=_get_agent,
        memory_store=memory_store,
    )
    workflow_planner = WorkflowPlanner(openrouter_client=openrouter_client)
    deps: dict[type, Any] = {
        WorkflowStore: workflow_store,
        WorkflowScheduler: workflow_scheduler,
        WorkflowPlanner: workflow_planner,
        PostgresGoalStore: goal_store,
        GoalPlanner: goal_planner,
        GoalExecutor: goal_executor,
        GoalSuggestionStore: goal_suggestion_store,
    }

    return AutomationStack(
        goal_store=goal_store,
        goal_suggestion_store=goal_suggestion_store,
        goal_planner=goal_planner,
        goal_executor=goal_executor,
        workflow_store=workflow_store,
        workflow_planner=workflow_planner,
        workflow_scheduler=workflow_scheduler,
        accountability_store=AccountabilityStore(pool=pool),
        deps=deps,
    )


def wire_goal_executor_push(
    stack: AutomationStack, notifier: ProactiveNotifier
) -> None:
    stack.goal_executor._push = notifier.push_notification
    stack.goal_executor._notify = notifier.notify


async def configure_workflow_executor(
    stack: AutomationStack,
    shared: Any,
    plugins: list,
    *,
    settings: Any,
    notifier: ProactiveNotifier,
    push_log_store: PushLogStore,
    checkpointer: Any,
    router: Any,
    persona_store: Any,
    workflow_graph_builder: Any,
) -> None:
    workflow_graph = workflow_graph_builder(
        checkpointer=checkpointer,
        plugins=plugins,
    )

    workflow_graph_config: dict = {
        "configurable": {
            "capability_gate": shared.capability_gate,
            "memory_store": shared.memory_store,
            "persona_store": persona_store,
            "openrouter_client": shared.openrouter_client,
            "embedder": shared.embedder,
            "settings": settings,
            "workflow_store": stack.workflow_store,
            "workflow_planner": stack.workflow_planner,
            "workflow_scheduler": stack.workflow_scheduler,
            "router": router,
        }
    }

    async def _workflow_executor(workflow: Any, execution_id: Any) -> None:
        from ze_agents.interface.types import RawInput as _RawInput
        from ze_core.conversation import make_graph_input
        from ze_core.telemetry.context import set_flow_context

        set_flow_context("workflow_execution", session_id=f"workflow:{workflow.id}")
        initial_state = {
            **make_graph_input(
                _RawInput(text=f"[workflow] {workflow.name}"),
                f"workflow:{workflow.id}",
            ),
            "workflow_id": workflow.id,
            "workflow_execution_id": execution_id,
            "workflow_steps": workflow.steps,
            "current_step_id": workflow.steps[0].id if workflow.steps else "",
            "workflow_step_results": [],
        }
        run_config = {
            **workflow_graph_config,
            "configurable": {
                **workflow_graph_config.get("configurable", {}),
                "thread_id": str(execution_id),
                "workflow_store": stack.workflow_store,
            },
        }
        await workflow_graph.ainvoke(initial_state, run_config)

    async def _workflow_failure_handler(workflow: Any, exc: Exception) -> None:
        alerts_cfg = settings.proactive_config.get("alerts", {})
        if not alerts_cfg.get("workflow_failure_enabled", True):
            return
        cooldown = int(alerts_cfg.get("workflow_failure_cooldown_hours", 1))
        event_type = f"workflow_failure:{workflow.id}"
        if await push_log_store.was_sent_within_hours(event_type, cooldown):
            log.info("failure_alert_suppressed_cooldown", workflow=workflow.name)
            return
        executions = await stack.workflow_store.list_executions(workflow.id, limit=1)
        execution = executions[0] if executions else None
        body = (
            execution.summary
            if execution and execution.summary
            else str(exc)
        )[:200]
        await notifier.notify(
            "workflow_failure",
            f'Workflow failed: "{workflow.name}"',
            body,
            source="workflows",
            target_type="workflow_run",
            target_id=str(workflow.id),
            urgency="high",
        )
        await push_log_store.log(event_type, workflow.name)
        log.info("failure_alert_sent", workflow=workflow.name)

    stack.workflow_scheduler.configure_executor(
        executor=_workflow_executor,
        on_failure=_workflow_failure_handler,
    )


def register_proactive_jobs(
    scheduler: ProactiveScheduler,
    settings: Any,
    stack: AutomationStack,
    *,
    notifier: ProactiveNotifier,
    push_log_store: PushLogStore,
) -> None:
    core_settings = settings.to_core_settings()
    wire_goal_executor_push(stack, notifier)

    async def _sweep_active_goals() -> None:
        goals = await stack.goal_store.list_for_advance()
        for g in goals:
            asyncio.create_task(stack.goal_executor.advance(g.id))

    scheduler.add_cron_job(
        fn=_sweep_active_goals,
        cron="*/15 * * * *",
        job_id="goal_advance_sweep",
    )
    log.info("goal_advance_sweep_scheduled")

    _goal_narrative = GoalNarrativeJob(
        notifier=notifier,
        push_log_store=push_log_store,
        goal_store=stack.goal_store,
        goal_planner=stack.goal_planner,
    )
    _goal_suggestion = GoalSuggestionJob(
        notifier=notifier,
        goal_store=stack.goal_store,
        suggestion_store=stack.goal_suggestion_store,
        planner=stack.goal_planner,
        memory_store=stack.goal_executor._memory,
    )
    _stuck_goals = StuckGoalJob(
        notifier=notifier,
        goal_store=stack.goal_store,
    )
    _accountability = AccountabilityJob(
        notifier=notifier,
        push_log_store=push_log_store,
        accountability_store=stack.accountability_store,
        goal_store=stack.goal_store,
        pool=stack.accountability_store._pool,
    )
    _cost_anomaly = CostAnomalyJob(
        notifier=notifier,
        accountability_store=stack.accountability_store,
        pool=stack.accountability_store._pool,
    )

    _proactive_cfg = core_settings.config.get("proactive", {})
    _narrative_cfg = _proactive_cfg.get("goal_narrative", {})
    if _narrative_cfg.get("enabled", True):
        scheduler.register(
            _goal_narrative,
            cron=_narrative_cfg.get("cron", "0 18 * * 0"),
        )
        log.info(
            "goal_narrative_scheduled", cron=_narrative_cfg.get("cron", "0 18 * * 0")
        )

    _suggestion_cfg = _proactive_cfg.get("goal_suggestion", {})
    if _suggestion_cfg.get("enabled", True):
        scheduler.register(
            _goal_suggestion,
            cron=_suggestion_cfg.get("cron", "0 19 * * 0"),
        )
        log.info(
            "goal_suggestion_scheduled", cron=_suggestion_cfg.get("cron", "0 19 * * 0")
        )

    _stuck_cfg = _proactive_cfg.get("stuck_goals", {})
    if _stuck_cfg.get("enabled", True):
        scheduler.register(
            _stuck_goals,
            cron=_stuck_cfg.get("cron", "0 9 * * 2"),
        )
        log.info("stuck_goals_scheduled", cron=_stuck_cfg.get("cron", "0 9 * * 2"))

    _acc_cfg = _proactive_cfg.get("accountability", {})
    if _acc_cfg.get("enabled", True):
        _accountability._stall_days = int(_acc_cfg.get("stall_days", 3))
        scheduler.register(
            _accountability,
            cron=_acc_cfg.get("schedule", "0 9 * * 1"),
        )
        log.info("accountability_scheduled", cron=_acc_cfg.get("schedule", "0 9 * * 1"))

        _cost_anomaly._threshold = float(_acc_cfg.get("anomaly_threshold", 4.0))
        _cost_anomaly._min_samples = int(_acc_cfg.get("anomaly_min_samples", 5))
        _cost_anomaly._retention_days = int(_acc_cfg.get("anomaly_retention_days", 30))
        scheduler.register(
            _cost_anomaly,
            cron=_acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"),
        )
        log.info(
            "cost_anomaly_scheduled",
            cron=_acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"),
        )
