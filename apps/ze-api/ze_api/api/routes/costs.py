from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ze_api.api.dependencies import get_container, require_api_key
from ze_api.api.schemas import AgentCostBucket, WebCostSummaryResponse
from ze_core.telemetry import rest as telemetry_rest

router = APIRouter(tags=["costs"], dependencies=[Depends(require_api_key)])


@router.get(
    "/summary",
    response_model=WebCostSummaryResponse,
    operation_id="getCostSummary",
    summary="Web cost summary",
    description=(
        "Aggregate LLM token usage and cost by agent for the web client costs screen. "
        "Defaults to the last 30 days."
    ),
)
async def web_cost_summary(container=Depends(get_container)) -> WebCostSummaryResponse:
    data = await telemetry_rest.web_cost_summary(container.pool)
    by_agent = {
        agent: AgentCostBucket.model_validate(bucket)
        for agent, bucket in data["by_agent"].items()
    }
    return WebCostSummaryResponse(
        total_usd=data["total_usd"],
        total_tokens=data["total_tokens"],
        total_calls=data["total_calls"],
        by_agent=by_agent,
        period=data["period"],
    )


@router.get(
    "/detail",
    operation_id="getCostDetail",
    summary="Cost detail",
    description=(
        "Aggregate LLM token usage and cost grouped by flow_type, agent, model, or session_id. "
        "Ordered by total_tokens descending."
    ),
)
async def cost_detail(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    group_by: str = Query(default="flow_type", description="Grouping dimension"),
    container=Depends(get_container),
) -> dict:
    try:
        return await telemetry_rest.cost_detail(container.pool, days=days, group_by=group_by)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
