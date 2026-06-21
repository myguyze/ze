from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import GoalListItem

router = APIRouter(tags=["goals"], dependencies=[Depends(require_api_key)])


@router.get(
    "/goals",
    response_model=list[GoalListItem],
    operation_id="listGoals",
    summary="List active goals",
    description="Returns active and awaiting-gate goals for the web client goals screen.",
)
async def list_goals(request: Request) -> list[GoalListItem]:
    store = request.app.state.container._plugin_stores.get("goal_store")
    if store is None:
        return []

    goals = await store.list_active()
    return [
        GoalListItem(
            id=goal.id,
            objective=goal.objective,
            status=goal.status.value,
            created_at=goal.created_at,
        )
        for goal in goals
        if goal.id is not None and goal.created_at is not None
    ]
