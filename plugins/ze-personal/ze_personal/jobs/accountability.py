from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ze_core.logging import get_logger
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.push_log_store import PushLogStore
from ze_personal.accountability.store import AccountabilityStore
from ze_personal.accountability.summarizer import build_narrative
from ze_personal.accountability.types import ActivitySummary, AgentCostSummary
from ze_personal.goals.store import GoalStore

log = get_logger(__name__)

_DEDUP_KEY = "weekly_accountability"
_DEDUP_HOURS = 6 * 24  # 6 days


@proactive_job
class AccountabilityJob:
    job_id = "weekly_accountability"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        accountability_store: AccountabilityStore,
        goal_store: GoalStore,
        pool: Any,
        *,
        stall_days: int = 3,
    ) -> None:
        self._notifier = notifier
        self._push_log = push_log_store
        self._acc_store = accountability_store
        self._goal_store = goal_store
        self._pool = pool
        self._stall_days = stall_days

    async def run(self) -> None:
        if await self._push_log.was_sent_within_hours(_DEDUP_KEY, _DEDUP_HOURS):
            log.info("accountability_job_skipped_dedup")
            return

        summary = await self._build_summary(period_days=7)
        narrative = build_narrative(summary)

        await self._notifier.push(narrative, urgency="low")
        await self._push_log.log(_DEDUP_KEY)
        log.info("accountability_job_sent", total_cost=summary.total_cost_usd)

    async def _build_summary(self, period_days: int) -> ActivitySummary:
        agent_costs: list[AgentCostSummary] = []
        total_cost = 0.0
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent,
                           COUNT(*)::int                       AS run_count,
                           COALESCE(SUM(total_tokens), 0)::int AS total_tokens,
                           COALESCE(SUM(cost_usd), 0)         AS cost_usd
                    FROM llm_cost_log
                    WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
                    GROUP BY agent
                    ORDER BY SUM(cost_usd) DESC NULLS LAST
                    """,
                    period_days,
                )
                total_row = await conn.fetchrow(
                    """
                    SELECT COALESCE(SUM(cost_usd), 0) AS total_cost
                    FROM llm_cost_log
                    WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
                    """,
                    period_days,
                )
            agent_costs = [
                AgentCostSummary(
                    agent=r["agent"],
                    run_count=r["run_count"],
                    total_tokens=r["total_tokens"],
                    cost_usd=float(r["cost_usd"]),
                )
                for r in rows
            ]
            total_cost = float(total_row["total_cost"] or 0)
        except Exception as exc:
            log.warning("accountability_cost_query_failed", error=str(exc))

        goals_advanced: list[str] = []
        goals_stalled: list[str] = []
        try:
            active_goals = await self._goal_store.list_active()
            cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
            stall_cutoff = datetime.now(timezone.utc) - timedelta(days=self._stall_days)
            for goal in active_goals:
                milestones = await self._goal_store.list_milestones(goal.id)
                for m in milestones:
                    if m.status.value == "completed" and m.completed_at is not None:
                        if m.completed_at >= cutoff:
                            goals_advanced.append(m.title)
                pending = [m for m in milestones if m.status.value == "pending"]
                if pending and all(m.created_at <= stall_cutoff for m in pending):
                    goals_stalled.append(goal.title)
        except Exception as exc:
            log.warning("accountability_goals_query_failed", error=str(exc))

        workflow_failures: list[str] = []
        try:
            failures = await self._push_log.list_workflow_failures_within_hours(period_days * 24)
            workflow_failures = [e.payload or "unknown" for e in failures]
        except Exception as exc:
            log.warning("accountability_workflow_query_failed", error=str(exc))

        anomalies: list[str] = []
        try:
            recs = await self._acc_store.list_anomalies_since(days=period_days)
            for rec in recs:
                anomalies.append(
                    f"{rec.agent} spent ${rec.run_cost_usd:.4f} on one run "
                    f"({rec.multiplier:.1f}× baseline) on {rec.detected_at[:10]}"
                )
        except Exception as exc:
            log.warning("accountability_anomalies_query_failed", error=str(exc))

        return ActivitySummary(
            period_days=period_days,
            agent_costs=agent_costs,
            goals_advanced=goals_advanced,
            goals_stalled=goals_stalled,
            workflow_failures=workflow_failures,
            anomalies=anomalies,
            total_cost_usd=total_cost,
        )
