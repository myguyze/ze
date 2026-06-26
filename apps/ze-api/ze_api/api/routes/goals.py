from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import (
    ExecutionTraceResponse,
    GateResponse,
    GoalActionResponse,
    GoalDetailResponse,
    GoalListItem,
    LearningResponse,
    MilestoneResponse,
)

router = APIRouter(tags=["goals"], dependencies=[Depends(require_api_key)])


@router.get(
    "/goals",
    response_model=list[GoalListItem],
    operation_id="listGoals",
    summary="List goals for the web client",
    description=(
        "Returns planning, active, awaiting-gate, and paused goals for the web client goals screen."
    ),
)
async def list_goals(request: Request) -> list[GoalListItem]:
    store = request.app.state.container._plugin_stores.get("goal_store")
    if store is None:
        return []

    goals = await store.list_for_display()
    return [
        GoalListItem(
            id=goal.id,
            title=goal.title,
            objective=goal.objective,
            status=goal.status.value,
            created_at=goal.created_at,
        )
        for goal in goals
        if goal.id is not None and goal.created_at is not None
    ]


@router.get(
    "/goals/{goal_id}",
    response_model=GoalDetailResponse,
    operation_id="getGoalDetail",
    summary="Get goal detail",
    description="Returns full goal detail including milestones, verification gates, and learnings.",
)
async def get_goal_detail(request: Request, goal_id: UUID) -> GoalDetailResponse:
    store = request.app.state.container._plugin_stores.get("goal_store")
    if store is None:
        raise HTTPException(status_code=503, detail="Goal engine unavailable")

    detail = await store.get_goal_detail(goal_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    g = detail.goal
    return GoalDetailResponse(
        id=g.id,
        title=g.title,
        objective=g.objective,
        success_condition=g.success_condition,
        status=g.status.value,
        type=g.type,
        time_horizon=g.time_horizon or None,
        learnings_summary=g.learnings or None,
        retrospective_text=g.retrospective_text,
        created_at=g.created_at,
        updated_at=g.updated_at,
        milestones=[
            MilestoneResponse(
                id=m.id,
                title=m.title,
                description=m.description,
                sequence=m.sequence,
                status=m.status.value,
                output=m.output or None,
                reuse_hint=m.reuse_hint or None,
                completed_at=m.completed_at,
                created_at=m.created_at,
            )
            for m in detail.milestones
        ],
        gates=[
            GateResponse(
                id=gate.id,
                after_sequence=gate.after_sequence,
                title=gate.title,
                status=gate.status.value,
                context_summary=gate.context_summary or None,
                plan_summary=gate.plan_summary or None,
                user_feedback=gate.user_feedback or None,
                fired_at=gate.fired_at,
                resolved_at=gate.resolved_at,
            )
            for gate in detail.gates
        ],
        learnings=[
            LearningResponse(
                id=lr.id,
                content=lr.content,
                source=lr.source,
                created_at=lr.created_at,
            )
            for lr in detail.learnings
        ],
    )


@router.get(
    "/goals/{goal_id}/traces",
    response_model=list[ExecutionTraceResponse],
    operation_id="listGoalTraces",
    summary="List goal execution traces",
    description="Returns execution traces for all milestones of a goal, ordered by seq ASC.",
)
async def list_goal_traces(
    request: Request,
    goal_id: UUID,
    milestone_id: UUID | None = Query(default=None, description="Filter to a single milestone"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> list[ExecutionTraceResponse]:
    store = request.app.state.container._plugin_stores.get("goal_store")
    if store is None:
        raise HTTPException(status_code=503, detail="Goal engine unavailable")

    traces = await store.list_traces(
        goal_id=goal_id,
        milestone_id=milestone_id,
        limit=limit,
        offset=offset,
    )
    return [
        ExecutionTraceResponse(
            id=t.id,
            milestone_id=t.milestone_id,
            goal_id=t.goal_id,
            seq=t.seq,
            tool_name=t.tool_name,
            args=t.args,
            result=t.result,
            duration_ms=t.duration_ms,
            success=t.success,
            error=t.error,
            created_at=t.created_at,
        )
        for t in traces
    ]


@router.post(
    "/goals/{goal_id}/start",
    response_model=GoalActionResponse,
    operation_id="startGoal",
    summary="Start a planned goal",
    description="Activates a goal in planning status and begins milestone execution.",
)
async def start_goal(request: Request, goal_id: UUID) -> GoalActionResponse:
    store = request.app.state.container._plugin_stores.get("goal_store")
    executor = request.app.state.container._plugin_stores.get("goal_executor")
    if store is None or executor is None:
        raise HTTPException(status_code=503, detail="Goal engine unavailable")

    if not await executor.approve_plan(goal_id):
        raise HTTPException(
            status_code=404,
            detail="Goal not found or not awaiting plan approval",
        )

    goal = await store.get_goal(goal_id)
    mgr = request.app.state.container.connection_manager
    await mgr.send_frame({"type": "refresh", "screen": "goals"})

    return GoalActionResponse(
        id=goal_id,
        status=goal.status.value if goal is not None else "active",
    )
