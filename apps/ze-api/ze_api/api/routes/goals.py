from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import GoalActionResponse, GoalListItem

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
