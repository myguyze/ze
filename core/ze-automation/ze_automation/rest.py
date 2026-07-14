from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.types import WorkflowStep
from ze_automation.workflow.validation import validate_workflow_steps


async def list_workflows(store: WorkflowStore) -> list[dict]:
    workflows = await store.list_all()
    return [
        {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "schedule": wf.schedule,
            "enabled": wf.enabled,
            "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
            "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
            "created_at": wf.created_at.isoformat(),
        }
        for wf in workflows
    ]


async def get_workflow(store: WorkflowStore, workflow_id: UUID) -> dict | None:
    wf = await store.get(workflow_id)
    if wf is None:
        return None
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "schedule": wf.schedule,
        "enabled": wf.enabled,
        "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
        "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
        "created_at": wf.created_at.isoformat(),
        "steps": [
            {
                "task": s.task,
                "agent_hint": s.agent_hint,
                "verify": s.verify,
                "intent": s.intent,
                "id": s.id,
                "branches": [
                    {"condition": b.condition, "to": b.to} for b in s.branches
                ],
                "default_next": s.default_next,
                "on_failure": s.on_failure,
            }
            for s in wf.steps
        ],
    }


async def list_workflow_executions(
    store: WorkflowStore, workflow_id: UUID
) -> list[dict]:
    executions = await store.list_executions(workflow_id)
    return [_execution_to_dict(ex) for ex in executions]


async def get_workflow_execution(
    store: WorkflowStore, workflow_id: UUID, execution_id: UUID
) -> dict | None:
    ex = await store.get_execution(workflow_id, execution_id)
    if ex is None:
        return None
    return _execution_to_dict(ex)


def _execution_to_dict(ex) -> dict:
    return {
        "id": ex.id,
        "workflow_id": ex.workflow_id,
        "status": ex.status,
        "step_results": [
            {
                "step_index": r.step_index,
                "task": r.task,
                "output": r.output,
                "success": r.success,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "step_id": r.step_id,
                "branch_taken": r.branch_taken,
                "attempt_count": r.attempt_count,
                "no_results": r.no_results,
            }
            for r in ex.step_results
        ],
        "error": ex.error,
        "summary": ex.summary,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "created_at": ex.created_at.isoformat(),
    }


async def build_status_summary(container: Any, *, period_days: int = 1) -> str:
    from datetime import datetime, timedelta, timezone

    from ze_automation.accountability.store import AccountabilityStore
    from ze_automation.accountability.summarizer import build_narrative
    from ze_automation.accountability.types import ActivitySummary, AgentCostSummary
    from ze_proactive.push_log_store import PushLogStore

    try:
        async with container.pool.acquire() as conn:
            cost_rows = await conn.fetch(
                """
                SELECT agent,
                       COUNT(*)::int        AS run_count,
                       SUM(total_tokens)    AS total_tokens,
                       COALESCE(SUM(cost_usd), 0) AS cost_usd
                FROM llm_cost_log
                WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
                GROUP BY agent
                ORDER BY SUM(cost_usd) DESC NULLS LAST
                """,
                period_days,
            )
            total_cost_row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(cost_usd), 0) AS total_cost
                FROM llm_cost_log
                WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
                """,
                period_days,
            )
    except Exception:
        cost_rows = []
        total_cost_row = None

    agent_costs = [
        AgentCostSummary(
            agent=r["agent"],
            run_count=r["run_count"],
            total_tokens=r["total_tokens"] or 0,
            cost_usd=float(r["cost_usd"]),
        )
        for r in cost_rows
    ]
    total_cost = float((total_cost_row or {}).get("total_cost", 0) or 0)

    goals_advanced: list[str] = []
    goals_stalled: list[str] = []
    try:
        goal_store = container._plugin_stores.get("goal_store")
        active_goals = await goal_store.list_active() if goal_store is not None else []
        for goal in active_goals:
            milestones = await goal_store.list_milestones(goal.id)
            for m in milestones:
                if m.status.value == "completed" and m.completed_at is not None:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
                    if m.completed_at >= cutoff:
                        goals_advanced.append(m.title)
            pending = [m for m in milestones if m.status.value == "pending"]
            if pending:
                stall_cutoff = datetime.now(timezone.utc) - timedelta(days=3)
                if all(m.created_at <= stall_cutoff for m in pending):
                    goals_stalled.append(goal.title)
    except Exception:
        pass

    workflow_failures: list[str] = []
    try:
        push_log = PushLogStore(pool=container.pool)
        failures = await push_log.list_workflow_failures_within_hours(period_days * 24)
        workflow_failures = [e.payload or "unknown" for e in failures]
    except Exception:
        pass

    anomalies: list[str] = []
    try:
        acc_store = AccountabilityStore(pool=container.pool)
        recs = await acc_store.list_anomalies_since(days=period_days)
        for rec in recs:
            anomalies.append(
                f"{rec.agent} spent ${rec.run_cost_usd:.4f} on one run "
                f"({rec.multiplier:.1f}× baseline) on {rec.detected_at[:10]}"
            )
    except Exception:
        pass

    summary = ActivitySummary(
        period_days=period_days,
        agent_costs=agent_costs,
        goals_advanced=goals_advanced,
        goals_stalled=goals_stalled,
        workflow_failures=workflow_failures,
        anomalies=anomalies,
        total_cost_usd=total_cost,
    )
    return build_narrative(summary)


async def update_workflow_steps(
    store: WorkflowStore, workflow_id: UUID, steps: list[WorkflowStep]
) -> dict:
    wf = await store.get(workflow_id)
    if wf is None:
        raise WorkflowPlanError(f"Workflow {workflow_id} not found")
    validate_workflow_steps(steps)
    await store.update_steps(workflow_id, steps)
    return await get_workflow(store, workflow_id)


async def cancel_workflow_execution(
    store: WorkflowStore,
    scheduler: Any,
    workflow_id: UUID,
    execution_id: UUID,
) -> dict:
    wf = await store.get(workflow_id)
    if wf is None:
        raise WorkflowPlanError(f"Workflow {workflow_id} not found")
    status = await scheduler.cancel_execution(workflow_id, execution_id)
    if status == "cancelled":
        message = "Cancellation requested; run will stop after the current step."
    else:
        message = "Execution is not in progress."
    return {
        "status": status,
        "execution_id": execution_id,
        "message": message,
    }
