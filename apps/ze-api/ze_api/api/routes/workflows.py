from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ze_agents.errors import WorkflowPlanError
from ze_api.api.dependencies import get_workflow_store, require_api_key
from ze_api.api.schemas import (
    CancelWorkflowExecutionResponse,
    StepResultResponse,
    TriggerWorkflowResponse,
    UpdateWorkflowStepsRequest,
    WorkflowDetailResponse,
    WorkflowExecutionResponse,
    WorkflowResponse,
    WorkflowRevisionResponse,
    WorkflowStepResponse,
)
from ze_automation import rest as workflow_rest
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.types import Branch, WorkflowStep

router = APIRouter(tags=["workflows"], dependencies=[Depends(require_api_key)])


@router.get(
    "",
    response_model=list[WorkflowResponse],
    operation_id="listWorkflows",
    summary="List workflows",
    description="Return all stored workflows, newest first.",
)
async def list_workflows(
    store: WorkflowStore = Depends(get_workflow_store),
) -> list[WorkflowResponse]:
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
            **{
                k: v
                for k, v in ex.items()
                if k not in ("step_results", "steps_snapshot")
            },
            step_results=[
                StepResultResponse.model_validate(r) for r in ex["step_results"]
            ],
            steps_snapshot=[
                WorkflowStepResponse.model_validate(s) for s in ex["steps_snapshot"]
            ],
        )
        for ex in executions
    ]


@router.get(
    "/{workflow_id}/executions/{execution_id}",
    response_model=WorkflowExecutionResponse,
    operation_id="getWorkflowExecution",
    summary="Get workflow execution",
    description="Return a single workflow execution by ID.",
)
async def get_workflow_execution(
    workflow_id: UUID,
    execution_id: UUID,
    store: WorkflowStore = Depends(get_workflow_store),
) -> WorkflowExecutionResponse:
    ex = await workflow_rest.get_workflow_execution(store, workflow_id, execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return WorkflowExecutionResponse(
        **{k: v for k, v in ex.items() if k not in ("step_results", "steps_snapshot")},
        step_results=[StepResultResponse.model_validate(r) for r in ex["step_results"]],
        steps_snapshot=[
            WorkflowStepResponse.model_validate(s) for s in ex["steps_snapshot"]
        ],
    )


@router.post(
    "/{workflow_id}/trigger",
    response_model=TriggerWorkflowResponse,
    operation_id="triggerWorkflow",
    summary="Trigger workflow",
    description="Start a workflow run immediately and return the execution ID.",
)
async def trigger_workflow(
    workflow_id: UUID,
    request: Request,
    store: WorkflowStore = Depends(get_workflow_store),
) -> TriggerWorkflowResponse:
    wf = await workflow_rest.get_workflow(store, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    scheduler = request.app.state.container.workflow_scheduler
    execution_id = await scheduler.trigger_now(workflow_id)
    return TriggerWorkflowResponse(
        status="triggered",
        workflow_id=workflow_id,
        execution_id=execution_id,
    )


def _steps_from_request(steps: list) -> list[WorkflowStep]:
    return [
        WorkflowStep(
            task=s.task,
            agent_hint=s.agent_hint,
            verify=s.verify,
            intent=s.intent,
            id=s.id,
            branches=[Branch(condition=b.condition, to=b.to) for b in s.branches],
            default_next=s.default_next,
            on_failure=s.on_failure,
        )
        for s in steps
    ]


@router.patch(
    "/{workflow_id}/steps",
    response_model=WorkflowDetailResponse,
    operation_id="updateWorkflowSteps",
    summary="Update workflow steps",
    description="Replace the full step list on an existing workflow. Schedule and run history are unchanged.",
)
async def update_workflow_steps(
    workflow_id: UUID,
    body: UpdateWorkflowStepsRequest,
    store: WorkflowStore = Depends(get_workflow_store),
) -> WorkflowDetailResponse:
    try:
        wf = await workflow_rest.update_workflow_steps(
            store, workflow_id, _steps_from_request(body.steps)
        )
    except WorkflowPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WorkflowDetailResponse(
        **{k: v for k, v in wf.items() if k != "steps"},
        steps=[WorkflowStepResponse.model_validate(s) for s in wf["steps"]],
    )


@router.get(
    "/{workflow_id}/revisions",
    response_model=list[WorkflowRevisionResponse],
    operation_id="listWorkflowRevisions",
    summary="List workflow revisions",
    description="Return the revision history for a workflow, newest first.",
)
async def list_workflow_revisions(
    workflow_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    store: WorkflowStore = Depends(get_workflow_store),
) -> list[WorkflowRevisionResponse]:
    wf = await workflow_rest.get_workflow(store, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    revisions = await workflow_rest.list_workflow_revisions(
        store, workflow_id, limit=limit, offset=offset
    )
    return [WorkflowRevisionResponse.model_validate(r) for r in revisions]


@router.post(
    "/{workflow_id}/executions/{execution_id}/cancel",
    response_model=CancelWorkflowExecutionResponse,
    operation_id="cancelWorkflowExecution",
    summary="Cancel workflow execution",
    description="Request cancellation of an in-progress run. Best-effort at step boundary.",
)
async def cancel_workflow_execution(
    workflow_id: UUID,
    execution_id: UUID,
    request: Request,
    store: WorkflowStore = Depends(get_workflow_store),
) -> CancelWorkflowExecutionResponse:
    scheduler = request.app.state.container.workflow_scheduler
    try:
        result = await workflow_rest.cancel_workflow_execution(
            store, scheduler, workflow_id, execution_id
        )
    except WorkflowPlanError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CancelWorkflowExecutionResponse.model_validate(result)
