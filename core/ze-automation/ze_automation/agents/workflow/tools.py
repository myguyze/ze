from __future__ import annotations

from datetime import datetime, timezone

from ze_agents.tool import ToolAccess, tool
from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.planner import WorkflowPlanner, validate_step_targets
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.types import StepResult, Workflow, WorkflowExecution
from ze_automation.workflow.scheduler import WorkflowScheduler


def _serialize_step_result(result: StepResult) -> dict:
    return {
        "step_index": result.step_index,
        "task": result.task,
        "output": result.output,
        "success": result.success,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


def _serialize_execution(execution: WorkflowExecution) -> dict:
    return {
        "status": execution.status,
        "step_results": [_serialize_step_result(r) for r in execution.step_results],
        "error": execution.error,
        "summary": execution.summary,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@tool(access=ToolAccess.READ, description="List all stored workflows with their status and schedule.")
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


@tool(access=ToolAccess.READ, description="Get full details of a workflow by name, including its steps.")
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
        "steps": [
            {"task": s.task, "agent_hint": s.agent_hint, "intent": s.intent}
            for s in wf.steps
        ],
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


@tool(access=ToolAccess.WRITE, description="Create a new workflow from a description with an optional recurring schedule.")
async def create_workflow(
    store: WorkflowStore,
    planner: WorkflowPlanner,
    scheduler: WorkflowScheduler,
    workflow_name: str,
    description: str,
    schedule_description: str = "",
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
    workflow_id = await store.create(workflow)
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


@tool(access=ToolAccess.WRITE, description="Enable a workflow by name so it runs on its schedule.")
async def enable_workflow(store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await store.set_enabled(wf.id, True)
    await scheduler.add_workflow(wf)
    return {"name": workflow_name, "enabled": True}


@tool(access=ToolAccess.WRITE, description="Disable a workflow by name so it stops running on its schedule.")
async def disable_workflow(store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await store.set_enabled(wf.id, False)
    await scheduler.remove_workflow(wf.id)
    return {"name": workflow_name, "enabled": False}


@tool(access=ToolAccess.WRITE, description="Permanently delete a workflow by name.")
async def delete_workflow(store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await scheduler.remove_workflow(wf.id)
    await store.delete(wf.id)
    return {"deleted": workflow_name}


@tool(access=ToolAccess.WRITE, description="Trigger a workflow to run immediately, outside its schedule.")
async def trigger_workflow(store: WorkflowStore, scheduler: WorkflowScheduler, workflow_name: str) -> dict:
    wf = await store.get_by_name(workflow_name)
    if wf is None:
        return {"error": f"No workflow named '{workflow_name}' found."}
    await scheduler.trigger_now(wf.id)
    return {"triggered": workflow_name}
