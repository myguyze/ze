from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ze_api.api.dependencies import get_container, require_api_key
from ze_api.api.schemas import (
    AgentCostBucket,
    CostAnomalyItem,
    CostAnomaliesResponse,
    DailyCostBucket,
    WebCostSummaryResponse,
)
from ze_agents.registry import get_registered_agents
from ze_automation.accountability.store import AccountabilityStore
from ze_core.telemetry import rest as telemetry_rest

router = APIRouter(tags=["costs"], dependencies=[Depends(require_api_key)])


def _build_agent_to_plugin_map() -> dict[str, str]:
    """Derive agent name -> owning package from each registered agent's module.

    Agents self-register via ``@agent`` at import time; there's no runtime link
    from an agent name back to its ``ZePlugin`` instance, so we key off the
    top-level package of the agent class's module (e.g. ``ze_calendar`` -> "calendar").
    """
    mapping: dict[str, str] = {}
    for name, cls in get_registered_agents().items():
        top_package = cls.__module__.split(".")[0]
        key = top_package[3:] if top_package.startswith("ze_") else top_package
        mapping[name] = key
    return mapping


def _aggregate_by_plugin(
    by_agent: dict[str, dict], agent_to_plugin: dict[str, str]
) -> dict[str, dict]:
    by_plugin: dict[str, dict] = {}
    for agent, bucket in by_agent.items():
        key = agent_to_plugin.get(agent, "other")
        target = by_plugin.setdefault(
            key,
            {"usd": 0.0, "tokens": 0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
        )
        target["usd"] += bucket["usd"]
        target["tokens"] += bucket["tokens"]
        target["calls"] += bucket["calls"]
        target["prompt_tokens"] += bucket["prompt_tokens"]
        target["completion_tokens"] += bucket["completion_tokens"]
    return by_plugin


@router.get(
    "/summary",
    response_model=WebCostSummaryResponse,
    operation_id="getCostSummary",
    summary="Web cost summary",
    description=(
        "Aggregate LLM token usage and cost by agent and by plugin for the web client "
        "costs screen. Defaults to the last 30 days."
    ),
)
async def web_cost_summary(container=Depends(get_container)) -> WebCostSummaryResponse:
    data = await telemetry_rest.web_cost_summary(container.pool)
    by_agent = {
        agent: AgentCostBucket.model_validate(bucket)
        for agent, bucket in data["by_agent"].items()
    }
    agent_to_plugin = _build_agent_to_plugin_map()
    by_plugin = {
        plugin: AgentCostBucket.model_validate(bucket)
        for plugin, bucket in _aggregate_by_plugin(data["by_agent"], agent_to_plugin).items()
    }
    by_day = [DailyCostBucket.model_validate(d) for d in data["by_day"]]
    return WebCostSummaryResponse(
        total_usd=data["total_usd"],
        total_tokens=data["total_tokens"],
        total_calls=data["total_calls"],
        by_agent=by_agent,
        by_plugin=by_plugin,
        by_day=by_day,
        period=data["period"],
    )


@router.get(
    "/anomalies",
    response_model=CostAnomaliesResponse,
    operation_id="getCostAnomalies",
    summary="Recent cost anomalies",
    description=(
        "Returns cost anomalies detected by the background job within the last N days. "
        "Anomalies are runs where an agent spent significantly more than its per-run median."
    ),
)
async def cost_anomalies(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    container=Depends(get_container),
) -> CostAnomaliesResponse:
    store = AccountabilityStore(pool=container.pool)
    records = await store.list_anomalies_since(days=days)
    return CostAnomaliesResponse(
        anomalies=[
            CostAnomalyItem(
                agent=r.agent,
                run_cost_usd=r.run_cost_usd,
                baseline_cost_usd=r.baseline_cost_usd,
                multiplier=r.multiplier,
                session_id=r.session_id,
                detected_at=r.detected_at,
            )
            for r in records
        ],
        period_days=days,
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
        return await telemetry_rest.cost_detail(
            container.pool, days=days, group_by=group_by
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
