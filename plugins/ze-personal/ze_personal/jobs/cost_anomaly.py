from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from ze_core.logging import get_logger
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_personal.accountability.store import AccountabilityStore
from ze_personal.accountability.types import AnomalyRecord

log = get_logger(__name__)

_DEDUP_WINDOW_HOURS = 24


@proactive_job
class CostAnomalyJob:
    job_id = "cost_anomaly"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        accountability_store: AccountabilityStore,
        pool: Any,
        *,
        anomaly_threshold: float = 4.0,
        min_samples: int = 5,
        retention_days: int = 30,
    ) -> None:
        self._notifier = notifier
        self._acc_store = accountability_store
        self._pool = pool
        self._threshold = anomaly_threshold
        self._min_samples = min_samples
        self._retention_days = retention_days

    async def run(self) -> None:
        await self._acc_store.clear_older_than(self._retention_days)

        try:
            async with self._pool.acquire() as conn:
                # Per-agent median baseline (30-day history, minimum min_samples runs).
                baseline_rows = await conn.fetch(
                    """
                    SELECT agent, cost_usd
                    FROM llm_cost_log
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                      AND cost_usd IS NOT NULL
                    ORDER BY agent, created_at DESC
                    """
                )
                # Runs in the past 24 hours with a known cost.
                recent_rows = await conn.fetch(
                    """
                    SELECT agent, session_id, cost_usd
                    FROM llm_cost_log
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                      AND cost_usd IS NOT NULL
                    """
                )
        except Exception as exc:
            log.warning("cost_anomaly_query_failed", error=str(exc))
            return

        # Build per-agent cost lists for baseline computation.
        agent_costs: dict[str, list[float]] = {}
        for row in baseline_rows:
            agent_costs.setdefault(row["agent"], []).append(float(row["cost_usd"]))

        # Collect session_ids that already have an anomaly record to avoid duplicate alerts.
        try:
            existing = await self._acc_store.list_anomalies_since(days=1)
            alerted_sessions = {r.session_id for r in existing if r.session_id}
        except Exception:
            alerted_sessions = set()

        for row in recent_rows:
            agent = row["agent"]
            run_cost = float(row["cost_usd"])
            session_id = row["session_id"]

            if session_id in alerted_sessions:
                continue

            history = agent_costs.get(agent, [])
            if len(history) < self._min_samples:
                # Not enough data to establish a baseline.
                continue

            baseline = statistics.median(history)
            if baseline <= 0:
                continue

            multiplier = run_cost / baseline
            if multiplier < self._threshold:
                continue

            rec = AnomalyRecord(
                agent=agent,
                run_cost_usd=run_cost,
                baseline_cost_usd=baseline,
                multiplier=round(multiplier, 2),
                session_id=session_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            await self._acc_store.record_anomaly(rec)
            alerted_sessions.add(session_id)

            text = (
                f"⚠️ Ze cost anomaly detected\n\n"
                f"The {agent} agent spent ${run_cost:.4f} on one run — "
                f"{multiplier:.1f}× its usual ${baseline:.4f}.\n"
                f"Date: {rec.detected_at[:10]}"
            )
            await self._notifier.push(text, urgency="high")
            log.info(
                "cost_anomaly_detected",
                agent=agent,
                run_cost=run_cost,
                baseline=baseline,
                multiplier=multiplier,
            )
