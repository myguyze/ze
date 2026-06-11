from fastapi import APIRouter, Depends, Query

from ze_api.api.dependencies import get_pool
from ze_api.api.schemas import RoutingLogEntry

router = APIRouter(tags=["routing"])


@router.get(
    "/log",
    response_model=list[RoutingLogEntry],
    summary="Routing log",
    description="Paginated routing decisions, newest first (offset-based pagination).",
)
async def get_routing_log(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
    pool=Depends(get_pool),
) -> list[RoutingLogEntry]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, session_id, prompt, method, primary_agent,
                   confidence, score_gap, is_compound, raw_scores,
                   created_at::text AS created_at
            FROM routing_log
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [RoutingLogEntry.model_validate(dict(r)) for r in rows]
