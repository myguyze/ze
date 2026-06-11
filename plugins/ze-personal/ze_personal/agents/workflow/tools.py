from __future__ import annotations

from datetime import datetime, timezone

from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.errors import WorkflowPlanError
from ze_personal.workflow.planner import WorkflowPlanner
from ze_personal.workflow.store import WorkflowStore
from ze_personal.workflow.types import Workflow
from ze_personal.workflow.scheduler import WorkflowScheduler


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
    return {
        "name": wf.name,
        "description": wf.description,
        "enabled": wf.enabled,
        "schedule": wf.schedule,
        "steps": [
            {"task": s.task, "agent_hint": s.agent_hint, "intent": s.intent}
            for s in wf.steps
        ],
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
