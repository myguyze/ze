import asyncio

from ze.logging import get_logger

_BATCH_SIZE = 50
_MIN_AGE_SECONDS = 120  # wait 2 min after creation before fetching — OpenRouter may lag

log = get_logger(__name__)


class CostReconciler:
    """Backfills cost_usd on llm_cost_log rows that have a generation_id but no cost yet."""

    def __init__(self, pool, sdk) -> None:
        self._pool = pool
        self._sdk = sdk  # OpenRouter SDK instance (from OpenRouterClient._sdk)

    async def run(self) -> None:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, generation_id
                FROM llm_cost_log
                WHERE cost_usd IS NULL
                  AND generation_id IS NOT NULL
                  AND created_at < NOW() - ($1 * INTERVAL '1 second')
                ORDER BY created_at ASC
                LIMIT $2
                """,
                _MIN_AGE_SECONDS,
                _BATCH_SIZE,
            )

        if not rows:
            return

        log.info("cost_reconcile_start", count=len(rows))
        updated = 0

        for row in rows:
            cost = await _fetch_cost(self._sdk, row["generation_id"])
            if cost is None:
                continue
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE llm_cost_log SET cost_usd = $1 WHERE id = $2",
                    cost,
                    row["id"],
                )
            updated += 1

        log.info("cost_reconcile_done", updated=updated, skipped=len(rows) - updated)


async def _fetch_cost(sdk, generation_id: str) -> float | None:
    try:
        resp = await sdk.generations.get_generation_async(id=generation_id)
        return resp.data.total_cost
    except Exception as exc:
        log.warning("cost_fetch_failed", generation_id=generation_id, error=str(exc))
        return None
