from __future__ import annotations

import asyncio
from typing import Any

from ze_core.logging import get_logger
from ze_core.telemetry.context import get_cost_context
from ze_core.telemetry.store import CostStore
from ze_core.telemetry.types import CostRecord

log = get_logger(__name__)


class CostTracker:
    def __init__(self, store: CostStore | None = None) -> None:
        self._store = store

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: int,
        generation_id: str | None = None,
        audio_seconds: float | None = None,
    ) -> None:
        """Schedule a fire-and-forget write without blocking the caller.

        If no store is configured, the record is logged but not persisted.
        """
        ctx = get_cost_context()
        rec = CostRecord(
            agent=ctx.agent,
            flow_type=ctx.flow_type,
            session_id=ctx.session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            cost_usd=None,
            generation_id=generation_id,
            audio_seconds=audio_seconds,
        )
        if self._store is None:
            log.info(
                "cost_record",
                agent=rec.agent,
                flow_type=rec.flow_type,
                model=rec.model,
                total_tokens=rec.total_tokens,
                duration_ms=rec.duration_ms,
            )
        else:
            asyncio.create_task(self._store.write(rec))
