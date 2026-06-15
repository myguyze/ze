from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_personal.goals.types import GoalStatus, MilestoneStatus


async def inject_goal_routing_context(state: dict[str, Any], config: RunnableConfig) -> dict:
    """Pre-route node: enrich state with active goal context for the embedding router."""
    goal_store = config["configurable"].get("goal_store")
    if goal_store is None:
        return {"routing_hints": None}

    try:
        hints = await _build_routing_hints(goal_store)
    except Exception:
        hints = None

    return {"routing_hints": hints or None}


async def _build_routing_hints(goal_store) -> str | None:
    active_goals = await goal_store.list_active()
    if not active_goals:
        return None

    parts = []
    for goal in active_goals[:3]:
        if goal.status == GoalStatus.AWAITING_GATE:
            gate = await goal_store.get_pending_gate(goal.id)
            label = f'"{goal.title}" — awaiting gate: {gate.title}' if gate else f'"{goal.title}" — awaiting gate'
        else:
            milestones = await goal_store.list_milestones(goal.id)
            current = next(
                (m for m in milestones if m.status == MilestoneStatus.IN_PROGRESS),
                next((m for m in milestones if m.status == MilestoneStatus.PENDING), None),
            )
            if current:
                label = f'"{goal.title}" — currently on step {current.sequence}: {current.title}'
            else:
                label = f'"{goal.title}"'
        parts.append(label)

    if not parts:
        return None

    hint = "[Active goals: " + " | ".join(parts) + "]"
    if len(hint) > 300:
        hint = hint[:297] + "…]"
    return hint
