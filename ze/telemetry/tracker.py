import asyncio

from ze.logging import get_logger
from ze.telemetry.context import get_cost_context
from ze.telemetry.types import CostRecord

_log = get_logger(__name__)


class CostTracker:
    def __init__(self, pool) -> None:
        self._pool = pool

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
        """Schedule a fire-and-forget DB write without blocking the caller."""
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
        asyncio.create_task(_write(self._pool, rec))


async def _write(pool, rec: CostRecord) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_cost_log
                    (session_id, agent, flow_type, model,
                     prompt_tokens, completion_tokens, total_tokens,
                     cost_usd, duration_ms, generation_id, audio_seconds)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                rec.session_id,
                rec.agent,
                rec.flow_type,
                rec.model,
                rec.prompt_tokens,
                rec.completion_tokens,
                rec.total_tokens,
                rec.cost_usd,
                rec.duration_ms,
                rec.generation_id,
                rec.audio_seconds,
            )
    except Exception as exc:
        _log.warning("cost_write_failed", error=str(exc))


