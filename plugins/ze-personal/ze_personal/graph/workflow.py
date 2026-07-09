"""Workflow graph nodes, edge functions, and graph builder.

Transitional location — will move to ze_personal/graph/workflow.py in the
ze-personal package once that package is created (arch-package-reorg step 4).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from ze_agents.types import GateDecision
from ze_agents.defaults import MODEL_WORKFLOW_VERIFY
from ze_logging import get_logger
from ze_core.orchestration.state import AgentState
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.types import StepResult, WorkflowStep

log = get_logger(__name__)

_TERMINAL_TARGETS = {"END", "FAIL"}
_MAX_STEP_VISITS = 4  # 1 initial + 3 revisits (FR-008)


class WorkflowAgentState(AgentState, total=False):
    """AgentState extension carrying workflow execution fields.

    Declared with total=False so checkpoints that predate this extension
    (plain conversation turns) remain valid without these keys.
    """
    workflow_id: UUID | None
    workflow_execution_id: UUID | None
    workflow_steps: list | None          # list[WorkflowStep]
    current_step_id: str
    steps_by_id: dict[str, WorkflowStep]
    visit_counts: dict[str, int]
    workflow_step_results: list          # list[StepResult]


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def load_workflow_step(state: dict[str, Any], config: RunnableConfig) -> dict:
    """Set prompt to the current step's task and reset all per-step state."""
    steps: list[WorkflowStep] = state["workflow_steps"]
    steps_by_id: dict[str, WorkflowStep] = state.get("steps_by_id") or {s.id: s for s in steps}
    current_step_id: str = state.get("current_step_id") or (steps[0].id if steps else "")
    step = steps_by_id[current_step_id]

    visit_counts = dict(state.get("visit_counts") or {})
    visit_counts[current_step_id] = visit_counts.get(current_step_id, 0) + 1

    log.info(
        "workflow_step_start",
        step_id=current_step_id,
        total=len(steps),
        task=step.task[:80],
        execution_id=str(state.get("workflow_execution_id")),
        visit_count=visit_counts[current_step_id],
    )

    return {
        "steps_by_id": steps_by_id,
        "current_step_id": current_step_id,
        "visit_counts": visit_counts,
        "prompt": step.task,
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "final_response": None,
    }


async def verify_step(state: dict[str, Any], config: RunnableConfig) -> dict:
    """Validate step output and append a StepResult. Routing to the next step happens in route_branch."""
    store: WorkflowStore = config["configurable"]["workflow_store"]
    client: Any = config["configurable"]["openrouter_client"]
    model = _resolve_verify_model(config)

    steps_by_id: dict[str, WorkflowStep] = state.get("steps_by_id") or {}
    step_id: str = state.get("current_step_id", "")
    step = steps_by_id[step_id]
    execution_id = state.get("workflow_execution_id")
    result = state.get("agent_result")
    subtask_results = state.get("subtask_results") or []
    prior = list(state.get("workflow_step_results") or [])
    exec_index = len(prior)

    tool_calls = list(result.tool_calls) if result and result.tool_calls else []
    for subtask_result in subtask_results:
        if subtask_result.tool_calls:
            tool_calls.extend(subtask_result.tool_calls)

    if tool_calls:
        failed = [tc for tc in tool_calls if not tc.success and not getattr(tc, "is_draft", False)]
        if failed:
            return await _fail_step(store, execution_id, state, exec_index, step_id, step.task, "", f"Tool {failed[0].tool_name} failed: {failed[0].error}")

    output = _resolve_step_output(state)
    if not output.strip():
        return await _fail_step(store, execution_id, state, exec_index, step_id, step.task, "", "Step produced empty output")

    if step.verify:
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
                model=model,
            )
            verdict = json.loads(raw)
            if not verdict.get("pass", True):
                reason = verdict.get("reason", "Verification failed")
                return await _fail_step(store, execution_id, state, exec_index, step_id, step.task, output, reason)
        except Exception as exc:
            log.warning("workflow_verify_error", step_id=step_id, error=str(exc))

    # Persistence (and branch_taken) is finalized by route_branch, which runs next and
    # knows whether/which branch matched — avoids writing this row twice.
    step_result = StepResult(
        step_index=exec_index,
        step_id=step_id,
        task=step.task,
        output=output,
        success=True,
        error=None,
        duration_ms=0,
    )

    log.info("workflow_step_complete", step_id=step_id, task=step.task[:60])
    return {
        "workflow_step_results": prior + [step_result],
    }


async def route_branch(state: dict[str, Any], config: RunnableConfig) -> dict:
    """Resolve the just-verified step's branches (if any) to the next step id, END, or FAIL.

    Also finalizes persistence of the last StepResult (branch_taken included) — verify_step
    builds the result but defers the write here so branch_taken lands on the same row.
    """
    store: WorkflowStore = config["configurable"]["workflow_store"]
    client: Any = config["configurable"]["openrouter_client"]
    model = _resolve_verify_model(config)

    steps: list[WorkflowStep] = state.get("workflow_steps") or []
    steps_by_id: dict[str, WorkflowStep] = state.get("steps_by_id") or {}
    step_results: list[StepResult] = list(state.get("workflow_step_results") or [])
    execution_id = state.get("workflow_execution_id")

    last_result = step_results[-1]
    step = steps_by_id[last_result.step_id]

    branch_taken: str | None = None
    target: str | None = None
    if step.branches:
        target, branch_taken = await _classify_branch(client, model, step, last_result.output)
    if target is None:
        target = step.default_next
    if target is None:
        target = _next_step_id_in_list(steps, step.id)
    if target is None:
        target = "END"

    last_result = replace(last_result, branch_taken=branch_taken)
    step_results[-1] = last_result
    if execution_id:
        await store.record_step(execution_id, last_result)

    visit_counts = dict(state.get("visit_counts") or {})
    if target not in _TERMINAL_TARGETS and visit_counts.get(target, 0) >= _MAX_STEP_VISITS:
        target_step = steps_by_id.get(target)
        task_label = target_step.task if target_step else target
        error_msg = (
            f"Loop limit exceeded for step {target} ({task_label}): "
            f"executed {_MAX_STEP_VISITS} times (1 initial + 3 revisits); "
            f"cannot revisit again."
        )
        log.warning(
            "workflow_loop_limit",
            step_id=target,
            visits=visit_counts.get(target, 0),
        )
        return {
            "workflow_step_results": step_results,
            "current_step_id": "FAIL",
            "visit_counts": visit_counts,
            "error": error_msg,
        }

    log.info("workflow_branch_routed", step_id=step.id, target=target, branch_taken=branch_taken)

    if target not in _TERMINAL_TARGETS:
        executed_ids = {r.step_id for r in step_results}
        asyncio.create_task(
            _sync_workflow_task_state(config, state, steps, executed_ids, step.task, "in_progress")
        )

    return {
        "workflow_step_results": step_results,
        "current_step_id": target,
        "visit_counts": visit_counts,
    }


async def workflow_synthesize(state: dict[str, Any], config: RunnableConfig) -> dict:
    """Merge all step outputs into a final response and mark execution complete."""
    store: WorkflowStore = config["configurable"]["workflow_store"]
    client: Any = config["configurable"]["openrouter_client"]
    model = _resolve_verify_model(config)

    step_results: list[StepResult] = state.get("workflow_step_results") or []
    execution_id = state.get("workflow_execution_id")

    parts = "\n\n".join(
        f"Step {r.step_index + 1} — {r.task}:\n{r.output}"
        for r in step_results
        if r.success and r.output
    )

    if parts:
        response = await client.complete(
            messages=[{
                "role": "user",
                "content": f"Summarize the following workflow results concisely:\n\n{parts}",
            }],
            model=model,
        )
    else:
        response = "Workflow completed with no output."

    if execution_id:
        await store.finish_execution(execution_id, "completed", summary=response)

    steps = state.get("workflow_steps") or []
    executed_ids = {r.step_id for r in step_results}
    last_task = step_results[-1].task if step_results else None
    asyncio.create_task(_sync_workflow_task_state(config, state, steps, executed_ids, last_task, "completed"))
    asyncio.create_task(_extract_and_store_workflow_procedure(config, state, step_results))
    log.info("workflow_complete", execution_id=str(execution_id), steps=len(step_results))
    return {"final_response": response}


async def workflow_failed(state: dict[str, Any], config: RunnableConfig) -> dict:
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
        await store.finish_execution(execution_id, "failed", error=error_msg)

    steps = state.get("workflow_steps") or []
    executed_ids = {r.step_id for r in step_results}
    last_task = step_results[-1].task if step_results else None
    asyncio.create_task(
        _sync_workflow_task_state(config, state, steps, executed_ids, last_task, "blocked", blocked_by=[error_msg])
    )
    log.warning("workflow_failed", execution_id=str(execution_id), error=error_msg)
    return {"final_response": f"Workflow failed: {error_msg}"}


# ── Edge functions ────────────────────────────────────────────────────────────

def after_capability_check_workflow(state: dict[str, Any]) -> str:
    """In workflow mode all steps execute directly — workflow creation was the gate."""
    decision = state.get("gate_decision")
    if decision == GateDecision.BLOCKED:
        return "workflow_failed"
    return "execute_tool"


def after_verify_step(state: dict[str, Any]) -> str:
    step_results = state.get("workflow_step_results") or []
    if step_results and not step_results[-1].success:
        return "workflow_failed"
    return "route_branch"


def after_route_branch(state: dict[str, Any]) -> str:
    target = state.get("current_step_id")
    if target == "END":
        return "workflow_synthesize"
    if target == "FAIL":
        return "workflow_failed"
    return "load_workflow_step"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_workflow_graph(checkpointer: Any, plugins: list | None = None) -> Any:
    """Build and compile the workflow execution graph."""
    from langgraph.constants import END

    from ze_core.orchestration.edges import after_embed_route
    from ze_core.orchestration.graph import graph_builder
    from ze_core.orchestration.state import build_state_type

    state_type = build_state_type(plugins or [])
    builder = graph_builder(state_type=state_type)

    builder.add_node("load_workflow_step", load_workflow_step)
    builder.add_node("verify_step",        verify_step)
    builder.add_node("route_branch",       route_branch)
    builder.add_node("workflow_synthesize", workflow_synthesize)
    builder.add_node("workflow_failed",    workflow_failed)

    builder.set_entry_point("load_workflow_step")

    builder.add_edge("load_workflow_step", "embed_route")
    builder.add_conditional_edges(
        "embed_route",
        after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context"},
    )
    builder.add_edge("decompose", "fetch_context")
    builder.add_edge("fetch_context",      "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        after_capability_check_workflow,
        {"execute_tool": "execute_tool", "workflow_failed": "workflow_failed"},
    )
    # Do NOT add execute_tool → write_memory here. The base graph already has
    # execute_tool → correlate (conditional). Adding a normal edge alongside it
    # creates a fan-out: both correlate AND write_memory fire after execute_tool,
    # causing verify_step to run twice per step — the early invocation sees the
    # next step index but no output, marking it as failed.
    builder.add_edge("write_memory",  "verify_step")
    builder.add_conditional_edges(
        "verify_step",
        after_verify_step,
        {
            "route_branch":        "route_branch",
            "workflow_failed":     "workflow_failed",
        },
    )
    builder.add_conditional_edges(
        "route_branch",
        after_route_branch,
        {
            "load_workflow_step":  "load_workflow_step",
            "workflow_synthesize": "workflow_synthesize",
            "workflow_failed":     "workflow_failed",
        },
    )
    builder.add_edge("workflow_synthesize", END)
    builder.add_edge("workflow_failed",     END)

    for plugin in (plugins or []):
        for name, fn in plugin.graph_nodes().items():
            builder.add_node(name, fn)
        plugin.graph_edges(builder)

    return builder.compile(checkpointer=checkpointer)


# ── Private helpers ───────────────────────────────────────────────────────────

def _resolve_step_output(state: dict[str, Any]) -> str:
    """Collect step text from whichever execution path populated state."""
    final = state.get("final_response")
    if final and str(final).strip():
        return str(final).strip()

    result = state.get("agent_result")
    if result and result.response and result.response.strip():
        return result.response.strip()

    subtask_results = state.get("subtask_results") or []
    parts = [
        r.response.strip()
        for r in subtask_results
        if r.response and r.response.strip()
    ]
    if parts:
        return "\n\n".join(parts)

    return ""


def _resolve_verify_model(config: RunnableConfig) -> str:
    cfg = config["configurable"].get("settings")
    if cfg is None:
        return MODEL_WORKFLOW_VERIFY
    models = (
        cfg.get("models", {})
        if isinstance(cfg, dict)
        else getattr(cfg, "config", {}).get("models", {})
    )
    return models.get("workflow_verify", MODEL_WORKFLOW_VERIFY)


async def _extract_and_store_workflow_procedure(
    config: RunnableConfig,
    state: dict[str, Any],
    step_results: list[StepResult],
) -> None:
    """Extract a reusable procedure from a completed workflow and store it with a graph link."""
    memory_store = config["configurable"].get("memory_store")
    workflow_planner = config["configurable"].get("workflow_planner")
    if memory_store is None or workflow_planner is None:
        return
    workflow_id = state.get("workflow_id")
    workflow_name = state.get("prompt") or "Unnamed workflow"
    try:
        procedure = await workflow_planner.extract_procedure(workflow_name, step_results)
    except Exception as exc:
        log.warning("workflow_procedure_extraction_failed", workflow_id=str(workflow_id), error=str(exc))
        return
    if procedure is None:
        return
    try:
        await memory_store.propose_procedure(
            procedure,
            linked_task_id=workflow_id,
            linked_task_type="workflow",
        )
        log.info("workflow_procedure_stored", workflow_id=str(workflow_id), name=procedure.name)
    except Exception as exc:
        log.warning("workflow_procedure_store_failed", workflow_id=str(workflow_id), error=str(exc))


async def _sync_workflow_task_state(
    config: RunnableConfig,
    state: dict[str, Any],
    steps: list[WorkflowStep],
    executed_step_ids: set[str],
    last_action: str | None,
    status: str,
    blocked_by: list[str] | None = None,
) -> None:
    """Write workflow execution progress to memory_task_state if a memory store is wired."""
    memory_store = config["configurable"].get("memory_store")
    if memory_store is None:
        return
    workflow_id = state.get("workflow_id")
    if workflow_id is None:
        return
    from ze_sdk.memory import TaskState
    from uuid import UUID
    try:
        open_steps = [s.task for s in steps if s.id not in executed_step_ids]
        next_action = open_steps[0] if open_steps else None
        await memory_store.upsert_task_state(TaskState(
            id=None,
            task_id=UUID(str(workflow_id)) if not isinstance(workflow_id, UUID) else workflow_id,
            goal_id=None,
            status=status,
            open_steps=open_steps,
            blocked_by=blocked_by or [],
            last_action=last_action,
            next_action=next_action,
        ))
    except Exception as exc:
        log.warning("workflow_task_state_sync_failed", workflow_id=str(workflow_id), error=str(exc))


def _next_step_id_in_list(steps: list[WorkflowStep], step_id: str) -> str | None:
    """The id of the step immediately after `step_id` in authored (list) order, or None if last."""
    ids = [s.id for s in steps]
    try:
        idx = ids.index(step_id)
    except ValueError:
        return None
    return ids[idx + 1] if idx + 1 < len(ids) else None


async def _classify_branch(
    client: Any,
    model: str,
    step: WorkflowStep,
    output: str,
) -> tuple[str | None, str | None]:
    """Ask the LLM which of the step's branches (if any) matches its output.

    Returns (target, condition_matched), or (None, None) if none matched or classification failed.
    """
    conditions = "\n".join(f"{i}. {b.condition}" for i, b in enumerate(step.branches))
    try:
        raw = await client.complete(
            messages=[{
                "role": "user",
                "content": (
                    f"Step output:\n{output}\n\n"
                    "Which of these conditions best matches the output? Reply with JSON only: "
                    '{"index": <int or null>}\n\n'
                    f"Conditions:\n{conditions}"
                ),
            }],
            model=model,
        )
        verdict = json.loads(raw)
        index = verdict.get("index")
        if isinstance(index, int) and 0 <= index < len(step.branches):
            branch = step.branches[index]
            return branch.to, branch.condition
    except Exception as exc:
        log.warning("workflow_branch_classify_error", step_id=step.id, error=str(exc))
    return None, None


async def _fail_step(
    store: WorkflowStore,
    execution_id: Any,
    state: dict[str, Any],
    exec_index: int,
    step_id: str,
    task: str,
    output: str,
    error: str,
) -> dict:
    step_result = StepResult(
        step_index=exec_index,
        step_id=step_id,
        task=task,
        output=output,
        success=False,
        error=error,
        duration_ms=0,
    )
    if execution_id:
        await store.record_step(execution_id, step_result)
    prior = list(state.get("workflow_step_results") or [])
    log.warning("workflow_step_failed", step_id=step_id, error=error)
    return {
        "workflow_step_results": prior + [step_result],
    }
