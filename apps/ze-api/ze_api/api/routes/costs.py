from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ze_api.api.dependencies import get_pool

router = APIRouter(tags=["costs"])

_VALID_GROUP_BY = {"flow_type", "agent", "model", "session_id"}


@router.get(
    "/summary",
    summary="Cost summary",
    description=(
        "Aggregate LLM token usage and cost grouped by flow_type, agent, model, or session_id. "
        "Ordered by total_tokens descending."
    ),
)
async def cost_summary(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    group_by: str = Query(default="flow_type", description="Grouping dimension"),
    pool=Depends(get_pool),
) -> dict:
    if group_by not in _VALID_GROUP_BY:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"group_by must be one of {sorted(_VALID_GROUP_BY)}")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                {group_by}                   AS grp,
                COUNT(*)::int                AS calls,
                SUM(prompt_tokens)::int      AS prompt_tokens,
                SUM(completion_tokens)::int  AS completion_tokens,
                SUM(total_tokens)::int       AS total_tokens,
                SUM(cost_usd)                AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY {group_by}
            ORDER BY SUM(total_tokens) DESC
            """,
            days,
        )

        totals = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int       AS total_calls,
                SUM(total_tokens)   AS total_tokens,
                SUM(cost_usd)       AS total_cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            """,
            days,
        )

    buckets = [
        {
            "group": row["grp"],
            "calls": row["calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["total_tokens"],
            "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None,
        }
        for row in rows
    ]

    return {
        "period_days": days,
        "group_by": group_by,
        "total_calls": totals["total_calls"] or 0,
        "total_tokens": int(totals["total_tokens"] or 0),
        "total_cost_usd": float(totals["total_cost_usd"]) if totals["total_cost_usd"] is not None else None,
        "buckets": buckets,
    }


async def _build_cost_summary(container: Any) -> str:
    """Return a plain-text cost summary for the past 7 days (used by WS costs command)."""
    async with container.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent,
                   COUNT(*)::int        AS run_count,
                   SUM(total_tokens)    AS total_tokens,
                   SUM(cost_usd)        AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY agent
            ORDER BY SUM(cost_usd) DESC NULLS LAST
            """
        )
        total = await conn.fetchrow(
            """
            SELECT SUM(cost_usd) AS total_cost, COUNT(*)::int AS total_runs
            FROM llm_cost_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        )

    if not rows and (not total or not total["total_runs"]):
        return "No LLM cost data for the past 7 days."

    total_cost = float(total["total_cost"] or 0)
    total_runs = total["total_runs"] or 0
    lines = [f"Cost summary — last 7 days: ${total_cost:.4f} across {total_runs} runs"]
    for row in rows:
        cost = float(row["cost_usd"] or 0)
        lines.append(f"  • {row['agent']}: {row['run_count']} runs, ${cost:.4f}")
    return "\n".join(lines)


async def _build_status_summary(container: Any, *, period_days: int = 1) -> str:
    """Build an on-demand accountability narrative (used by WS /status command)."""
    from ze_personal.accountability.store import AccountabilityStore
    from ze_personal.accountability.summarizer import build_narrative
    from ze_personal.accountability.types import ActivitySummary, AgentCostSummary

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
        active_goals = await container.goal_store.list_active()
        for goal in active_goals:
            milestones = await container.goal_store.list_milestones(goal.id)
            for m in milestones:
                if m.status.value == "completed" and m.completed_at is not None:
                    from datetime import timedelta
                    from datetime import timezone as _tz
                    from datetime import datetime as _dt
                    cutoff = _dt.now(_tz.utc) - timedelta(days=period_days)
                    if m.completed_at >= cutoff:
                        goals_advanced.append(m.title)
            pending = [m for m in milestones if m.status.value == "pending"]
            if pending:
                from datetime import timedelta as _td, datetime as _dt2, timezone as _tz2
                stall_cutoff = _dt2.now(_tz2.utc) - _td(days=3)
                if all(m.created_at <= stall_cutoff for m in pending):
                    goals_stalled.append(goal.title)
    except Exception:
        pass

    workflow_failures: list[str] = []
    try:
        from ze_core.proactive.push_log_store import PushLogStore
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
