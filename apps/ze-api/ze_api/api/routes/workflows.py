from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ze_api.api.dependencies import get_workflow_store
from ze_personal.workflow.store import WorkflowStore

router = APIRouter(tags=["workflows"])


class StepResultResponse(BaseModel):
    step_index: int
    task: str
    output: str
    success: bool
    error: str | None
    duration_ms: int


class WorkflowStepResponse(BaseModel):
    task: str
    agent_hint: str | None
    verify: str | None


class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    description: str
    schedule: str | None
    enabled: bool
    last_run_at: str | None
    next_run_at: str | None
    created_at: str


class WorkflowDetailResponse(WorkflowResponse):
    steps: list[WorkflowStepResponse]


class WorkflowExecutionResponse(BaseModel):
    id: UUID
    workflow_id: UUID | None
    status: str
    step_results: list[StepResultResponse]
    error: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str


@router.get(
    "",
    response_model=list[WorkflowResponse],
    summary="List workflows",
    description="Return all stored workflows, newest first.",
)
async def list_workflows(store: WorkflowStore = Depends(get_workflow_store)) -> list[WorkflowResponse]:
    workflows = await store.list_all()
    return [
        WorkflowResponse(
            id=wf.id,
            name=wf.name,
            description=wf.description,
            schedule=wf.schedule,
            enabled=wf.enabled,
            last_run_at=wf.last_run_at.isoformat() if wf.last_run_at else None,
            next_run_at=wf.next_run_at.isoformat() if wf.next_run_at else None,
            created_at=wf.created_at.isoformat(),
        )
        for wf in workflows
    ]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailResponse,
    summary="Get workflow detail",
    description="Return a single workflow with its full step list.",
)
async def get_workflow(
    workflow_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> WorkflowDetailResponse:
    wf = await store.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowDetailResponse(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        schedule=wf.schedule,
        enabled=wf.enabled,
        last_run_at=wf.last_run_at.isoformat() if wf.last_run_at else None,
        next_run_at=wf.next_run_at.isoformat() if wf.next_run_at else None,
        created_at=wf.created_at.isoformat(),
        steps=[WorkflowStepResponse(task=s.task, agent_hint=s.agent_hint, verify=s.verify) for s in wf.steps],
    )


@router.get(
    "/{workflow_id}/executions",
    response_model=list[WorkflowExecutionResponse],
    summary="List workflow executions",
    description="Return the 20 most recent executions for a workflow.",
)
async def list_executions(
    workflow_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> list[WorkflowExecutionResponse]:
    executions = await store.list_executions(workflow_id)
    return [
        WorkflowExecutionResponse(
            id=ex.id,
            workflow_id=ex.workflow_id,
            status=ex.status,
            step_results=[
                StepResultResponse(
                    step_index=r.step_index,
                    task=r.task,
                    output=r.output,
                    success=r.success,
                    error=r.error,
                    duration_ms=r.duration_ms,
                )
                for r in ex.step_results
            ],
            error=ex.error,
            started_at=ex.started_at.isoformat() if ex.started_at else None,
            completed_at=ex.completed_at.isoformat() if ex.completed_at else None,
            created_at=ex.created_at.isoformat(),
        )
        for ex in executions
    ]


@router.post(
    "/{workflow_id}/trigger",
    response_model=dict,
    summary="Trigger workflow",
    description="Run a stored workflow immediately outside its schedule.",
)
async def trigger_workflow(
    workflow_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict:
    wf = await store.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "triggered", "workflow_id": str(workflow_id)}
