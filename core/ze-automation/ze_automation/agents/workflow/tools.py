from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from ze_agents.tool import ToolAccess, tool
from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.planner import WorkflowPlanner, validate_step_targets
from ze_automation.workflow.validation import validate_workflow_steps
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.types import (
    ActorContext,
    ActorSource,
    Branch,
    StepResult,
    Workflow,
    WorkflowExecution,
    WorkflowStep,
)
from ze_automation.workflow.scheduler import WorkflowScheduler


def _build_actor(session_id: str | None, user_message_id: str | None) -> ActorContext:
    if session_id is None or user_message_id is None:
        return ActorContext(source=ActorSource.SYSTEM)
    return ActorContext(
        source=ActorSource.AGENT,
        session_id=session_id,
        user_message_id=user_message_id,
    )


def _serialize_step_result(result: StepResult) -> dict:
    return {
        "step_index": result.step_index,
        "task": result.task,
        "output": result.output,
        "success": result.success,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "step_id": result.step_id,
        "branch_taken": result.branch_taken,
        "attempt_count": result.attempt_count,
        "no_results": result.no_results,
    }


def _serialize_step(step: WorkflowStep) -> dict:
    return {
        "task": step.task,
        "agent_hint": step.agent_hint,
        "intent": step.intent,
        "id": step.id,
        "branches": [{"condition": b.condition, "to": b.to} for b in step.branches],
        "default_next": step.default_next,
        "on_failure": step.on_failure,
    }


def _serialize_execution(execution: WorkflowExecution) -> dict:
    return {
        "status": execution.status,
        "step_results": [_serialize_step_result(r) for r in execution.step_results],
        "error": execution.error,
        "summary": execution.summary,
        "started_at": execution.started_at.isoformat()
        if execution.started_at
        else None,
        "completed_at": execution.completed_at.isoformat()
        if execution.completed_at
        else None,
    }


@tool(
    access=ToolAccess.READ,
    description="List all stored workflows with their status and schedule.",
)
async def list_workflows(store: WorkflowStore) -> list:
    workflows = await store.list_all()
    return [
        {
            "name": wf.name,
            "description": wf.description,
            "enabled": wf.enabled,
            "schedule": wf.schedule,
            "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
            "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
        }
        for wf in workflows
    ]


@tool(
    access=ToolAccess.READ,
    description="Get full details of a workflow by name, including its steps.",
)
async def get_workflow(store: WorkflowStore, workflow_name: str) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    recent = await store.list_executions(wf.id, limit=1)
    return {
        "name": wf.name,
        "description": wf.description,
        "enabled": wf.enabled,
        "schedule": wf.schedule,
        "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
        "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
        "steps": [_serialize_step(s) for s in wf.steps],
        "last_execution": _serialize_execution(recent[0]) if recent else None,
    }


@tool(
    access=ToolAccess.READ,
    description="List recent execution runs for a workflow, including status, step results, and errors.",
)
async def list_workflow_executions(
    store: WorkflowStore,
    workflow_name: str,
    limit: int = 5,
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    executions = await store.list_executions(wf.id, limit=limit)
    return {
        "workflow_name": wf.name,
        "executions": [_serialize_execution(ex) for ex in executions],
    }


@tool(
    access=ToolAccess.WRITE,
    description="Create a new workflow from a description with an optional recurring schedule.",
)
async def create_workflow(
    store: WorkflowStore,
    planner: WorkflowPlanner,
    scheduler: WorkflowScheduler,
    workflow_name: str,
    description: str,
    schedule_description: str = "",
    session_id: str | None = None,
    user_message_id: str | None = None,
) -> dict:
    try:
        steps = await planner.plan(description)
        validate_step_targets(steps)
        schedule = await planner.extract_schedule(schedule_description or description)
    except WorkflowPlanError as exc:
        return {"error": f"Couldn't plan the workflow: {exc}"}

    next_run = None
    if schedule:
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(schedule)
        next_run = trigger.get_next_fire_time(None, datetime.now(tz=timezone.utc))

    workflow = Workflow(
        id=None,  # type: ignore[arg-type]
        name=workflow_name,
        description=description,
        steps=steps,
        schedule=schedule,
        enabled=True,
        last_run_at=None,
        next_run_at=next_run,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    actor = _build_actor(session_id, user_message_id)
    workflow_id = await store.create(workflow, actor=actor)
    workflow.id = workflow_id
    await scheduler.add_workflow(workflow)

    return {
        "name": workflow_name,
        "steps": [s.task for s in steps],
        "schedule": schedule,
    }


@tool(
    access=ToolAccess.WRITE,
    description="Update a workflow's recurring schedule from a natural-language description.",
)
async def update_workflow(
    store: WorkflowStore,
    planner: WorkflowPlanner,
    scheduler: WorkflowScheduler,
    workflow_name: str,
    schedule_description: str,
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    try:
        schedule = await planner.extract_schedule(schedule_description)
    except WorkflowPlanError as exc:
        return {"error": f"Couldn't parse the schedule: {exc}"}

    next_run = None
    if schedule:
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(schedule)
        next_run = trigger.get_next_fire_time(None, datetime.now(tz=timezone.utc))

    await store.update_schedule(wf.id, schedule, next_run)
    await scheduler.remove_workflow(wf.id)

    if schedule and wf.enabled:
        wf.schedule = schedule
        wf.next_run_at = next_run
        await scheduler.add_workflow(wf)

    return {
        "name": workflow_name,
        "schedule": schedule,
        "next_run_at": next_run.isoformat() if next_run else None,
    }


@tool(
    access=ToolAccess.WRITE,
    description="Enable a workflow by name so it runs on its schedule.",
)
async def enable_workflow(
    store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await store.set_enabled(wf.id, True)
    await scheduler.add_workflow(wf)
    return {"name": workflow_name, "enabled": True}


@tool(
    access=ToolAccess.WRITE,
    description="Disable a workflow by name so it stops running on its schedule.",
)
async def disable_workflow(
    store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await store.set_enabled(wf.id, False)
    await scheduler.remove_workflow(wf.id)
    return {"name": workflow_name, "enabled": False}


@tool(access=ToolAccess.WRITE, description="Permanently delete a workflow by name.")
async def delete_workflow(
    store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await scheduler.remove_workflow(wf.id)
    await store.delete(wf.id)
    return {"deleted": workflow_name}


@tool(
    access=ToolAccess.WRITE,
    description="Trigger a workflow to run immediately, outside its schedule.",
)
async def trigger_workflow(
    store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await scheduler.trigger_now(wf.id)
    return {"triggered": workflow_name}


@tool(
    access=ToolAccess.WRITE,
    description="Replace the step list on an existing workflow without changing its schedule.",
)
async def edit_workflow_steps(
    store: WorkflowStore,
    workflow_name: str,
    steps_json: str,
    session_id: str | None = None,
    user_message_id: str | None = None,
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}

    try:
        raw_steps = json.loads(steps_json)
        if not isinstance(raw_steps, list):
            raise ValueError("steps_json must be a JSON array")
        steps = [
            WorkflowStep(
                task=item["task"],
                agent_hint=item.get("agent_hint"),
                verify=item.get("verify"),
                intent=item.get("intent", "execute"),
                id=item["id"],
                branches=[
                    Branch(condition=b["condition"], to=b["to"])
                    for b in item.get("branches") or []
                ],
                default_next=item.get("default_next"),
                on_failure=item.get("on_failure", "fail"),
            )
            for item in raw_steps
        ]
        validate_workflow_steps(steps)
        actor = _build_actor(session_id, user_message_id)
        await store.update_steps(wf.id, steps, actor=actor)
    except (json.JSONDecodeError, KeyError, ValueError, WorkflowPlanError) as exc:
        return {"error": str(exc)}

    return {
        "name": workflow_name,
        "step_count": len(steps),
        "steps": [_serialize_step(s) for s in steps],
    }


@tool(
    access=ToolAccess.WRITE,
    description="Cancel an in-progress workflow run by name (latest running execution).",
)
async def cancel_workflow_run(
    store: WorkflowStore,
    scheduler: WorkflowScheduler,
    workflow_name: str,
    execution_id: str = "",
) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}

    target_id: UUID | None = None
    if execution_id:
        try:
            target_id = UUID(execution_id)
        except ValueError:
            return {"error": f"Invalid execution_id '{execution_id}'."}
    else:
        executions = await store.list_executions(wf.id, limit=5)
        running = next((ex for ex in executions if ex.status == "running"), None)
        if running is None:
            return {
                "status": "not_running",
                "message": "No in-progress execution found for this workflow.",
            }
        target_id = running.id

    status = await scheduler.cancel_execution(wf.id, target_id)
    if status == "cancelled":
        message = "Cancellation requested; run will stop after the current step."
    else:
        message = "Execution is not in progress."
    return {
        "status": status,
        "execution_id": str(target_id),
        "message": message,
    }
