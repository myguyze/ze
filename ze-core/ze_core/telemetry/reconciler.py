from __future__ import annotations

from typing import Any

from ze_core.logging import get_logger
from ze_core.telemetry.postgres import PostgresCostStore

_BATCH_SIZE = 50
_MIN_AGE_SECONDS = 120

log = get_logger(__name__)


class CostReconciler:
    """Backfills cost_usd on llm_cost_log rows that have a generation_id but no cost yet.

    Requires a PostgresCostStore and an OpenRouterClient. Rows are processed in
    batches of up to 50, skipping any less than 2 minutes old (OpenRouter may lag).
    """

    def __init__(self, store: PostgresCostStore, openrouter_client: Any) -> None:
        self._store = store
        self._client = openrouter_client

    async def run(self) -> None:
        rows = await self._store.fetch_pending(_BATCH_SIZE, _MIN_AGE_SECONDS)

        if not rows:
            return

        log.info("cost_reconcile_start", count=len(rows))
        updated = 0

        for row in rows:
            cost = await self._client.fetch_generation_cost(row["generation_id"])
            if cost is None:
                continue
            await self._store.update_cost(row["id"], cost)
            updated += 1

        log.info("cost_reconcile_done", updated=updated, skipped=len(rows) - updated)
