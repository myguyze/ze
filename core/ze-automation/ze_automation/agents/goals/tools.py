from __future__ import annotations

import asyncio
import html as _html
from uuid import UUID

from ze_agents.tool import ToolAccess, tool
from ze_agents.errors import GoalPlanError
from ze_automation.goals.executor import GoalExecutor
from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.postgres import PostgresGoalStore as GoalStore
from ze_automation.goals.types import Goal, GoalStatus, MilestoneStatus
from ze_agents.interface.types import Action, Notification
from ze_logging import get_logger
from ze_sdk.proactive import ProactiveNotifier

log = get_logger(__name__)


@tool(access=ToolAccess.WRITE, description="Redirect a running goal with new instructions. Ze will finish its current step and then replan the remaining milestones incorporating your direction.")
async def steer_goal(executor: GoalExecutor, goal_id: str, instruction: str) -> str:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return f"Invalid goal ID: {goal_id!r}"
    ok = await executor.steer(uid, instruction)
    if not ok:
        return "That goal is not currently active. Use list_goals to check status."
    return "Got it — I'll apply that direction after the current step finishes."


@tool(access=ToolAccess.READ, description="List all goals with their current status.")
async def list_goals(store: GoalStore) -> list:
    goals = await store.list_all()
    return [
        {
            "id": str(g.id),
            "title": g.title,
            "status": g.status.value,
            "objective": g.objective[:120],
            "type": g.type,
        }
        for g in goals
    ]


@tool(access=ToolAccess.READ, description="Get full status of a goal by its ID, including milestones and pending gate.")
async def get_goal_status(store: GoalStore, goal_id: str) -> dict:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return {"error": f"Invalid goal ID: {goal_id!r}"}

    goal = await store.get_goal(uid)
    if not goal:
        return {"error": f"Goal not found: {goal_id}"}

    milestones = await store.list_milestones(uid)
    gate = await store.get_pending_gate(uid)

    completed = sum(1 for m in milestones if m.status == MilestoneStatus.COMPLETED)
    skipped = sum(1 for m in milestones if m.status.value == "skipped")
    total = len(milestones)

    result: dict = {
        "id": str(goal.id),
        "title": goal.title,
        "status": goal.status.value,
        "objective": goal.objective,
        "progress": f"{completed}/{total} milestones done" + (f" ({skipped} skipped)" if skipped else ""),
        "milestones": [
            {"sequence": m.sequence, "title": m.title, "status": m.status.value}
            for m in milestones
        ],
        "pending_gate": gate.title if gate else None,
    }
    if goal.learnings:
        result["learnings"] = goal.learnings[:500]
    return result


async def _check_convergence(
    store: GoalStore,
    planner: GoalPlanner,
    notifier: ProactiveNotifier,
    new_goal: Goal,
    active_goals: list[Goal],
) -> None:
    others = [g for g in active_goals if g.id != new_goal.id]
    if not others:
        return
    try:
        conv = await planner.detect_convergence(new_goal, others)
    except Exception as exc:
        log.warning("goal_convergence_check_failed", error=str(exc))
        return
    if conv is None:
        return
    log.info(
        "goal_convergence_detected",
        new_goal_id=str(new_goal.id),
        overlapping_goal_id=str(conv.overlapping_goal_id),
    )
    await notifier.push_notification(Notification(
        content=(
            f"<b>Goal overlap detected</b>\n\n"
            f"<b>{_html.escape(new_goal.title)}</b> and "
            f"<b>{_html.escape(conv.overlapping_goal_title)}</b> share scope: "
            f"{_html.escape(conv.overlap_description)}\n\n"
            f"Suggested approach: <i>{_html.escape(conv.suggestion)}</i>. "
            f"Let me know if you'd like to share outputs between them, sequence one "
            f"after the other, or keep them running independently."
        ),
        format="html",
        urgency="normal",
    ))


@tool(access=ToolAccess.WRITE, description="Create a new goal and propose a milestone plan for user approval.")
async def create_goal(
    store: GoalStore,
    planner: GoalPlanner,
    notifier: ProactiveNotifier,
    goal_title: str,
    objective: str,
    success_condition: str,
    time_horizon: str = "",
    goal_type: str = "custom",
) -> dict:
    active_goals = await store.list_active()

    goal = Goal(
        title=goal_title,
        objective=objective,
        success_condition=success_condition,
        time_horizon=time_horizon,
        type=goal_type,
        status=GoalStatus.PLANNING,
    )

    try:
        prior_work = await store.list_completed_milestone_summaries(
            days=90,
            limit=20,
            exclude_goal_id=None,
        )
    except Exception as exc:
        log.warning("goal_prior_work_query_failed", error=str(exc))
        prior_work = []

    try:
        milestones, gates = await planner.plan(goal, prior_work=prior_work or None)
    except GoalPlanError as exc:
        return {"error": f"Couldn't plan the goal: {exc}"}

    goal = await store.create_goal(goal)

    for m in milestones:
        m.goal_id = goal.id
    for g in gates:
        g.goal_id = goal.id

    for m in milestones:
        await store.create_milestone(m)
    for g in gates:
        await store.create_gate(g)

    step_summary = "\n".join(f"  {m.sequence}. {m.title}" for m in milestones)
    gate_summary = (
        "\n".join(f"  Gate after step {g.after_sequence}: {g.title}" for g in gates)
        or "  (none)"
    )

    plan_text = (
        f"🎯 <b>{_html.escape(goal_title)}</b> — proposed plan\n\n"
        f"<b>Milestones:</b>\n{_html.escape(step_summary)}\n\n"
        f"<b>Checkpoints:</b>\n{_html.escape(gate_summary)}\n\n"
        "Start this goal?"
    )
    await notifier.push_notification(
        Notification(
            content=plan_text,
            format="html",
            urgency="high",
            actions=[
                Action(label="Start goal", payload=f"goal_plan:yes:{goal.id}"),
                Action(label="Cancel", payload=f"goal_plan:no:{goal.id}"),
            ],
        )
    )

    asyncio.create_task(_check_convergence(store, planner, notifier, goal, active_goals))

    return {
        "id": str(goal.id),
        "title": goal_title,
        "milestones": len(milestones),
        "gates": len(gates),
    }


@tool(access=ToolAccess.WRITE, description="Pause an active goal by its ID.")
async def pause_goal(store: GoalStore, goal_id: str) -> dict:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return {"error": f"Invalid goal ID: {goal_id!r}"}
    goal = await store.get_goal(uid)
    if not goal:
        return {"error": f"Goal not found: {goal_id}"}
    await store.update_status(uid, GoalStatus.PAUSED)
    return {"title": goal.title, "status": "paused"}


@tool(access=ToolAccess.WRITE, description="Resume a paused goal by its ID and continue execution.")
async def resume_goal(store: GoalStore, executor: GoalExecutor, goal_id: str) -> dict:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return {"error": f"Invalid goal ID: {goal_id!r}"}
    goal = await store.get_goal(uid)
    if not goal:
        return {"error": f"Goal not found: {goal_id}"}
    if goal.status != GoalStatus.PAUSED:
        return {"error": f"Goal '{goal.title}' is not paused (status: {goal.status.value})."}
    await store.update_status(uid, GoalStatus.ACTIVE)
    asyncio.create_task(executor.advance(uid))
    return {"title": goal.title, "status": "active"}


@tool(access=ToolAccess.READ, description="Return the execution trace for a specific milestone — what tools Ze called and what they returned.")
async def get_milestone_trace(store: GoalStore, goal_id: str, milestone_sequence: int) -> str:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return f"Invalid goal ID: {goal_id!r}"

    milestones = await store.list_milestones(uid)
    target = next((m for m in milestones if m.sequence == milestone_sequence), None)
    if target is None:
        return f"No milestone with sequence {milestone_sequence} found for goal {goal_id}."

    traces = await store.list_traces(goal_id=uid, milestone_id=target.id)
    if not traces:
        return "No execution trace recorded for this milestone."

    lines = [f"Execution trace for milestone {milestone_sequence}: {target.title}\n"]
    for t in traces:
        status = "OK" if t.success else f"FAILED ({t.error})"
        lines.append(f"  [{t.seq}] {t.tool_name} ({t.duration_ms}ms) — {status}")
        if t.args:
            import json as _json
            lines.append(f"       args: {_json.dumps(t.args)[:200]}")
        lines.append(f"       result: {t.result[:300]}")
    return "\n".join(lines)


@tool(access=ToolAccess.WRITE, description="Abandon a goal permanently by its ID.")
async def abandon_goal(store: GoalStore, goal_id: str) -> dict:
    try:
        uid = UUID(goal_id)
    except ValueError:
        return {"error": f"Invalid goal ID: {goal_id!r}"}
    goal = await store.get_goal(uid)
    if not goal:
        return {"error": f"Goal not found: {goal_id}"}
    await store.update_status(uid, GoalStatus.ABANDONED)
    return {"title": goal.title, "status": "abandoned"}
