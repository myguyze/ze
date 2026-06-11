from __future__ import annotations

from typing import Any

from ze_core.logging import get_logger
from ze_personal.accountability.types import AnomalyRecord

log = get_logger(__name__)


class AccountabilityStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def record_anomaly(self, rec: AnomalyRecord) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO accountability_anomalies
                        (agent, run_cost_usd, baseline_usd, multiplier, session_id, detected_at)
                    VALUES ($1, $2, $3, $4, $5, $6::timestamptz)
                    """,
                    rec.agent,
                    rec.run_cost_usd,
                    rec.baseline_cost_usd,
                    rec.multiplier,
                    rec.session_id,
                    rec.detected_at,
                )
        except Exception as exc:
            log.warning("accountability_record_anomaly_failed", error=str(exc))

    async def list_anomalies_since(self, days: int) -> list[AnomalyRecord]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT agent, run_cost_usd, baseline_usd, multiplier, session_id, detected_at
                    FROM accountability_anomalies
                    WHERE detected_at >= NOW() - ($1 * INTERVAL '1 day')
                    ORDER BY detected_at DESC
                    """,
                    days,
                )
            return [
                AnomalyRecord(
                    agent=r["agent"],
                    run_cost_usd=float(r["run_cost_usd"]),
                    baseline_cost_usd=float(r["baseline_usd"]),
                    multiplier=float(r["multiplier"]),
                    session_id=r["session_id"],
                    detected_at=r["detected_at"].isoformat(),
                )
                for r in rows
            ]
        except Exception as exc:
            log.warning("accountability_list_anomalies_failed", error=str(exc))
            return []

    async def clear_older_than(self, days: int) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM accountability_anomalies WHERE detected_at < NOW() - ($1 * INTERVAL '1 day')",
                    days,
                )
        except Exception as exc:
            log.warning("accountability_clear_failed", error=str(exc))
