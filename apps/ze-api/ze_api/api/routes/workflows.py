from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ze_api.api.dependencies import get_workflow_store, require_api_key
from ze_api.api.schemas import (
    StepResultResponse,
    WorkflowDetailResponse,
    WorkflowExecutionResponse,
    WorkflowResponse,
    WorkflowStepResponse,
)
from ze_automation import rest as workflow_rest
from ze_automation.workflow.store import WorkflowStore

router = APIRouter(tags=["workflows"], dependencies=[Depends(require_api_key)])


@router.get(
    "",
    response_model=list[WorkflowResponse],
    operation_id="listWorkflows",
    summary="List workflows",
    description="Return all stored workflows, newest first.",
)
async def list_workflows(store: WorkflowStore = Depends(get_workflow_store)) -> list[WorkflowResponse]:
    workflows = await workflow_rest.list_workflows(store)
    return [WorkflowResponse.model_validate(wf) for wf in workflows]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailResponse,
    operation_id="getWorkflow",
    summary="Get workflow detail",
    description="Return a single workflow with its full step list.",
)
async def get_workflow(
    workflow_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> WorkflowDetailResponse:
    wf = await workflow_rest.get_workflow(store, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowDetailResponse(
        **{k: v for k, v in wf.items() if k != "steps"},
        steps=[WorkflowStepResponse.model_validate(s) for s in wf["steps"]],
    )


@router.get(
    "/{workflow_id}/executions",
    response_model=list[WorkflowExecutionResponse],
    operation_id="listWorkflowExecutions",
    summary="List workflow executions",
    description="Return the 20 most recent executions for a workflow.",
)
async def list_workflow_executions(
    workflow_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> list[WorkflowExecutionResponse]:
    executions = await workflow_rest.list_workflow_executions(store, workflow_id)
    return [
        WorkflowExecutionResponse(
            **{k: v for k, v in ex.items() if k != "step_results"},
            step_results=[StepResultResponse.model_validate(r) for r in ex["step_results"]],
        )
        for ex in executions
    ]


@router.post(
    "/{workflow_id}/trigger",
    response_model=dict,
    operation_id="triggerWorkflow",
    summary="Trigger workflow",
    description="Run a stored workflow immediately outside its schedule.",
)
async def trigger_workflow(
    workflow_id: UUID,
    request: Request,
    store: WorkflowStore = Depends(get_workflow_store),
) -> dict:
    wf = await workflow_rest.get_workflow(store, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    scheduler = request.app.state.container.workflow_scheduler
    await scheduler.trigger_now(workflow_id)
    return {"status": "triggered", "workflow_id": str(workflow_id)}
