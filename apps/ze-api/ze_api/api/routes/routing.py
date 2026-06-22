from fastapi import APIRouter, Depends, Query

from ze_api.api.dependencies import get_container, require_api_key
from ze_api.api.schemas import RoutingLogEntry
from ze_core.routing import rest as routing_rest

router = APIRouter(tags=["routing"], dependencies=[Depends(require_api_key)])


@router.get(
    "/log",
    response_model=list[RoutingLogEntry],
    operation_id="getRoutingLog",
    summary="Routing log",
    description="Paginated routing decisions, newest first (offset-based pagination).",
)
async def get_routing_log(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
    container=Depends(get_container),
) -> list[RoutingLogEntry]:
    rows = await routing_rest.list_routing_log(container.pool, limit=limit, offset=offset)
    return [RoutingLogEntry.model_validate(r) for r in rows]
