import asyncio
import json

from langchain_core.runnables import RunnableConfig

from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze.telemetry.context import set_agent_context
from ze.workflow.store import WorkflowStore
from ze.workflow.types import StepResult, WorkflowStep

log = get_logger(__name__)


async def load_workflow_step(state: AgentState, config: RunnableConfig) -> dict:
    """Set prompt to the current step's task and reset all per-step state."""
    steps: list[WorkflowStep] = state["workflow_steps"]
    idx: int = state.get("current_step_index", 0)
    step = steps[idx]

    log.info(
        "workflow_step_start",
        step_index=idx,
        total=len(steps),
        task=step.task[:80],
        execution_id=str(state.get("workflow_execution_id")),
    )

    return {
        "prompt": step.task,
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
    }


async def verify_step(state: AgentState, config: RunnableConfig) -> dict:
    """Validate step output; append StepResult and advance index."""
    from ze.openrouter.client import OpenRouterClient
    from ze.settings import Settings

    store: WorkflowStore = config["configurable"]["workflow_store"]
    client: OpenRouterClient = config["configurable"]["openrouter_client"]
    settings: Settings = config["configurable"]["settings"]

    steps: list[WorkflowStep] = state["workflow_steps"]
    idx: int = state.get("current_step_index", 0)
    step = steps[idx]
    execution_id = state.get("workflow_execution_id")
    result = state.get("agent_result")

    # 1. Tool success check
    if result and result.tool_calls:
        failed = [tc for tc in result.tool_calls if not tc.success and not getattr(tc, "is_draft", False)]
        if failed:
            return _fail_step(store, execution_id, state, idx, step.task, "", f"Tool {failed[0].tool_name} failed: {failed[0].error}")

    # 2. Non-empty output check
    output = result.response if result else ""
    if not output.strip():
        return _fail_step(store, execution_id, state, idx, step.task, "", "Step produced empty output")

    # 3. Criteria check
    if step.verify:
        set_agent_context("workflow_verify")
        try:
            raw = await client.complete(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Step output:\n{output}\n\n"
                        f"Verification criteria: {step.verify}\n\n"
                        'Does the output meet the criteria? Reply with JSON only: {"pass": true, "reason": "..."}'
                    ),
                }],
                model=settings.workflow_verify_model,
            )
            verdict = json.loads(raw)
            if not verdict.get("pass", True):
                reason = verdict.get("reason", "Verification failed")
                return _fail_step(store, execution_id, state, idx, step.task, output, reason)
        except Exception as exc:
            log.warning("workflow_verify_error", step_index=idx, error=str(exc))

    # All checks passed
    step_result = StepResult(
        step_index=idx,
        task=step.task,
        output=output,
        success=True,
        error=None,
        duration_ms=0,
    )
    asyncio.create_task(store.record_step(execution_id, step_result))

    prior = list(state.get("workflow_step_results") or [])
    log.info("workflow_step_complete", step_index=idx, task=step.task[:60])
    return {
        "workflow_step_results": prior + [step_result],
        "current_step_index": idx + 1,
    }


async def workflow_synthesize(state: AgentState, config: RunnableConfig) -> dict:
    """Merge all step outputs into a final response and mark execution complete."""
    from ze.openrouter.client import OpenRouterClient
    from ze.settings import Settings

    store: WorkflowStore = config["configurable"]["workflow_store"]
    client: OpenRouterClient = config["configurable"]["openrouter_client"]
    settings: Settings = config["configurable"]["settings"]

    step_results: list[StepResult] = state.get("workflow_step_results") or []
    execution_id = state.get("workflow_execution_id")

    parts = "\n\n".join(
        f"Step {r.step_index + 1} — {r.task}:\n{r.output}"
        for r in step_results
        if r.success and r.output
    )

    if parts:
        set_agent_context("workflow_synthesize")
        response = await client.complete(
            messages=[{
                "role": "user",
                "content": f"Summarize the following workflow results concisely:\n\n{parts}",
            }],
            model=settings.workflow_verify_model,
        )
    else:
        response = "Workflow completed with no output."

    if execution_id:
        asyncio.create_task(store.finish_execution(execution_id, "completed"))

    log.info("workflow_complete", execution_id=str(execution_id), steps=len(step_results))
    return {"final_response": response}


async def workflow_failed(state: AgentState, config: RunnableConfig) -> dict:
    """Record execution failure and build a user-facing error message."""
    store: WorkflowStore = config["configurable"]["workflow_store"]

    step_results: list[StepResult] = state.get("workflow_step_results") or []
    execution_id = state.get("workflow_execution_id")

    failed = [r for r in step_results if not r.success]
    if failed:
        last = failed[-1]
        error_msg = f"Step {last.step_index + 1} ({last.task}) failed: {last.error}"
    else:
        error_msg = state.get("error") or "Workflow failed"

    if execution_id:
        asyncio.create_task(store.finish_execution(execution_id, "failed", error=error_msg))

    log.warning("workflow_failed", execution_id=str(execution_id), error=error_msg)
    return {"final_response": f"Workflow failed: {error_msg}"}


# ── Helper ────────────────────────────────────────────────────────────────────

def _fail_step(
    store: WorkflowStore,
    execution_id,
    state: AgentState,
    idx: int,
    task: str,
    output: str,
    error: str,
) -> dict:
    step_result = StepResult(
        step_index=idx,
        task=task,
        output=output,
        success=False,
        error=error,
        duration_ms=0,
    )
    asyncio.create_task(store.record_step(execution_id, step_result))
    prior = list(state.get("workflow_step_results") or [])
    log.warning("workflow_step_failed", step_index=idx, error=error)
    return {
        "workflow_step_results": prior + [step_result],
        "current_step_index": idx + 1,
    }
