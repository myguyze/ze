from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from ze_core.logging import get_logger
from ze_core.routing.types import RoutingEnvelope

log = get_logger(__name__)


@runtime_checkable
class RoutingStore(Protocol):
    async def write_log(
        self, session_id: str, prompt: str, envelope: RoutingEnvelope
    ) -> None: ...


class PostgresRoutingStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def write_log(
        self, session_id: str, prompt: str, envelope: RoutingEnvelope
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO routing_log
                        (session_id, prompt, method, primary_agent,
                         confidence, score_gap, is_compound, raw_scores,
                         complexity, model_selected)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)
                    """,
                    session_id,
                    prompt,
                    envelope.routing_method,
                    envelope.primary_agent,
                    envelope.confidence,
                    envelope.score_gap,
                    envelope.is_compound,
                    json.dumps(envelope.raw_scores),
                    envelope.complexity,
                    envelope.subtasks[0].model if envelope.subtasks else None,
                )
        except Exception as exc:
            log.warning("routing_log_write_failed", error=str(exc))
