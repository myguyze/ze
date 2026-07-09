import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_agents.types import AgentResult, ToolCall
from ze_automation.workflow.types import Branch, StepResult, WorkflowStep
from ze_personal.graph.workflow import (
    _resolve_step_output,
    after_route_branch,
    after_verify_step,
    load_workflow_step,
    route_branch,
    verify_step,
    workflow_failed,
)


def _make_store() -> MagicMock:
    store = MagicMock()
    store.record_step = AsyncMock()
    return store


def test_resolve_step_output_prefers_final_response():
    state = {
        "final_response": "synthesized",
        "agent_result": AgentResult(agent="news", response="ignored"),
    }
    assert _resolve_step_output(state) == "synthesized"


def test_resolve_step_output_uses_agent_result():
    state = {
        "agent_result": AgentResult(agent="news", response="headlines"),
        "subtask_results": [AgentResult(agent="news", response="fallback")],
    }
    assert _resolve_step_output(state) == "headlines"


def test_resolve_step_output_joins_subtask_results():
    state = {
        "subtask_results": [
            AgentResult(agent="news", response="first"),
            AgentResult(agent="research", response="second"),
        ],
    }
    assert _resolve_step_output(state) == "first\n\nsecond"


@pytest.mark.asyncio
async def test_verify_step_accepts_subtask_results_without_agent_result():
    store = _make_store()
    config = {
        "configurable": {
            "workflow_store": store,
            "openrouter_client": MagicMock(),
        }
    }
    step = WorkflowStep(task="search news", intent="read", id="s0")
    state = {
        "workflow_steps": [step],
        "steps_by_id": {"s0": step},
        "current_step_id": "s0",
        "workflow_execution_id": uuid4(),
        "workflow_step_results": [],
        "agent_result": None,
        "subtask_results": [AgentResult(agent="news", response="article summary")],
    }

    result = await verify_step(state, config)

    assert len(result["workflow_step_results"]) == 1
    assert result["workflow_step_results"][0].success is True
    assert result["workflow_step_results"][0].output == "article summary"
    assert result["workflow_step_results"][0].step_id == "s0"


@pytest.mark.asyncio
async def test_verify_step_fails_when_all_outputs_empty():
    store = _make_store()
    config = {
        "configurable": {
            "workflow_store": store,
            "openrouter_client": MagicMock(),
        }
    }
    step = WorkflowStep(task="search news", intent="read", id="s0")
    state = {
        "workflow_steps": [step],
        "steps_by_id": {"s0": step},
        "current_step_id": "s0",
        "workflow_execution_id": uuid4(),
        "workflow_step_results": [],
        "agent_result": AgentResult(agent="news", response=""),
        "subtask_results": [],
    }

    result = await verify_step(state, config)

    assert result["workflow_step_results"][-1].success is False
    assert result["workflow_step_results"][-1].error == "Step produced empty output"
    assert result["workflow_step_results"][-1].step_id == "s0"


class TestRouteBranch:
    def _client(self, response: str) -> MagicMock:
        client = MagicMock()
        client.complete = AsyncMock(return_value=response)
        return client

    async def test_routes_to_matching_branch_and_skips_the_other(self):
        step_a = WorkflowStep(
            task="Check invoice",
            id="s0",
            branches=[
                Branch(condition="invoice found", to="s1"),
                Branch(condition="no invoice", to="s2"),
            ],
        )
        step_b = WorkflowStep(task="Process invoice", id="s1")
        step_c = WorkflowStep(task="Send reminder", id="s2")
        steps = [step_a, step_b, step_c]
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        client = self._client(json.dumps({"index": 0}))
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(step_index=0, step_id="s0", task="Check invoice", output="found an invoice", success=True, error=None, duration_ms=0)
            ],
            "workflow_execution_id": uuid4(),
        }

        result = await route_branch(state, config)

        assert result["current_step_id"] == "s1"
        assert result["current_step_id"] != "s2"
        assert result["workflow_step_results"][-1].branch_taken == "invoice found"
        store.record_step.assert_called_once()

    async def test_no_branches_continues_sequentially(self):
        step_a = WorkflowStep(task="Fetch news", id="s0")
        step_b = WorkflowStep(task="Summarize", id="s1")
        steps = [step_a, step_b]
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        client = MagicMock()
        client.complete = AsyncMock()
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(step_index=0, step_id="s0", task="Fetch news", output="headlines", success=True, error=None, duration_ms=0)
            ],
            "workflow_execution_id": uuid4(),
        }

        result = await route_branch(state, config)

        assert result["current_step_id"] == "s1"
        assert result["workflow_step_results"][-1].branch_taken is None
        client.complete.assert_not_called()

    async def test_no_branches_but_default_next_overrides_list_order(self):
        step_a = WorkflowStep(task="Fetch news", id="s0", default_next="s2")
        step_b = WorkflowStep(task="Summarize", id="s1")
        step_c = WorkflowStep(task="Send digest", id="s2")
        steps = [step_a, step_b, step_c]
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        client = MagicMock()
        client.complete = AsyncMock()
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(step_index=0, step_id="s0", task="Fetch news", output="headlines", success=True, error=None, duration_ms=0)
            ],
            "workflow_execution_id": uuid4(),
        }

        result = await route_branch(state, config)

        assert result["current_step_id"] == "s2"

    async def test_last_step_with_no_target_resolves_to_end(self):
        step_a = WorkflowStep(task="Send digest", id="s0")
        steps = [step_a]
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        client = MagicMock()
        client.complete = AsyncMock()
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(step_index=0, step_id="s0", task="Send digest", output="done", success=True, error=None, duration_ms=0)
            ],
            "workflow_execution_id": uuid4(),
        }

        result = await route_branch(state, config)

        assert result["current_step_id"] == "END"
        assert after_route_branch(result) == "workflow_synthesize"


class TestFailurePrecedesRouting:
    async def test_failed_step_routes_to_workflow_failed_and_never_reaches_route_branch(self):
        store = _make_store()
        config = {
            "configurable": {
                "workflow_store": store,
                "openrouter_client": MagicMock(),
            }
        }
        step = WorkflowStep(
            task="Check invoice",
            id="s0",
            branches=[Branch(condition="invoice found", to="s1")],
        )
        state = {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "current_step_id": "s0",
            "workflow_execution_id": uuid4(),
            "workflow_step_results": [],
            "agent_result": AgentResult(agent="finance", response=""),
            "subtask_results": [],
        }

        result = await verify_step(state, config)

        assert result["workflow_step_results"][-1].success is False
        assert after_verify_step(result) == "workflow_failed"
        assert after_verify_step(result) != "route_branch"

    async def test_failed_tool_call_routes_to_workflow_failed(self):
        store = _make_store()
        config = {
            "configurable": {
                "workflow_store": store,
                "openrouter_client": MagicMock(),
            }
        }
        step = WorkflowStep(task="Send email", id="s0")
        failed_call = ToolCall(tool_name="send_email", args={}, result=None, duration_ms=0, success=False, error="SMTP error")
        state = {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "current_step_id": "s0",
            "workflow_execution_id": uuid4(),
            "workflow_step_results": [],
            "agent_result": AgentResult(agent="email", response="sent", tool_calls=[failed_call]),
            "subtask_results": [],
        }

        result = await verify_step(state, config)

        assert result["workflow_step_results"][-1].success is False
        assert after_verify_step(result) == "workflow_failed"


class TestLoopGuard:
    def _client(self, response: str) -> MagicMock:
        client = MagicMock()
        client.complete = AsyncMock(return_value=response)
        return client

    def _loop_step(self) -> WorkflowStep:
        return WorkflowStep(
            task="Retry until done",
            id="s0",
            branches=[Branch(condition="not done yet", to="s0")],
        )

    async def _run_route_cycle(
        self,
        *,
        steps: list[WorkflowStep],
        step_results: list[StepResult],
        visit_counts: dict[str, int],
        client: MagicMock,
    ) -> tuple[dict, dict[str, int]]:
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": step_results,
            "workflow_execution_id": uuid4(),
            "visit_counts": visit_counts,
        }
        result = await route_branch(state, config)
        return result, dict(result.get("visit_counts") or visit_counts)

    async def test_self_loop_fails_after_fourth_execution(self):
        step = self._loop_step()
        steps = [step]
        client = self._client(json.dumps({"index": 0}))
        visit_counts: dict[str, int] = {}
        step_results: list[StepResult] = []

        for i in range(3):
            loaded = await load_workflow_step(
                {
                    "workflow_steps": steps,
                    "steps_by_id": {"s0": step},
                    "current_step_id": "s0",
                    "visit_counts": visit_counts,
                    "workflow_execution_id": uuid4(),
                },
                {"configurable": {}},
            )
            visit_counts = loaded["visit_counts"]
            step_results.append(
                StepResult(
                    step_index=i,
                    step_id="s0",
                    task=step.task,
                    output="still not done",
                    success=True,
                    error=None,
                    duration_ms=0,
                )
            )
            result, visit_counts = await self._run_route_cycle(
                steps=steps,
                step_results=step_results,
                visit_counts=visit_counts,
                client=client,
            )
            assert result["current_step_id"] == "s0"
            assert after_route_branch(result) == "load_workflow_step"

        loaded = await load_workflow_step(
            {
                "workflow_steps": steps,
                "steps_by_id": {"s0": step},
                "current_step_id": "s0",
                "visit_counts": visit_counts,
                "workflow_execution_id": uuid4(),
            },
            {"configurable": {}},
        )
        visit_counts = loaded["visit_counts"]
        step_results.append(
            StepResult(
                step_index=3,
                step_id="s0",
                task=step.task,
                output="still not done",
                success=True,
                error=None,
                duration_ms=0,
            )
        )
        result, _ = await self._run_route_cycle(
            steps=steps,
            step_results=step_results,
            visit_counts=visit_counts,
            client=client,
        )

        assert result["current_step_id"] == "FAIL"
        assert after_route_branch(result) == "workflow_failed"
        assert "s0" in result["error"]
        assert "loop limit" in result["error"].lower()
        assert len(step_results) == 4

        failed = await workflow_failed(result, {"configurable": {"workflow_store": _make_store()}})
        assert "loop limit" in failed["final_response"].lower()
        assert "Retry until done" in failed["final_response"]

    async def test_loop_exits_forward_before_limit(self):
        step_a = WorkflowStep(
            task="Poll source",
            id="s0",
            branches=[
                Branch(condition="no answer yet", to="s0"),
                Branch(condition="answer found", to="s1"),
            ],
        )
        step_b = WorkflowStep(task="Summarize answer", id="s1")
        steps = [step_a, step_b]
        client = MagicMock()
        client.complete = AsyncMock(
            side_effect=[
                json.dumps({"index": 0}),
                json.dumps({"index": 0}),
                json.dumps({"index": 1}),
            ]
        )
        visit_counts: dict[str, int] = {}
        step_results: list[StepResult] = []

        for i, output in enumerate(["waiting", "waiting again"]):
            loaded = await load_workflow_step(
                {
                    "workflow_steps": steps,
                    "steps_by_id": {"s0": step_a, "s1": step_b},
                    "current_step_id": "s0",
                    "visit_counts": visit_counts,
                    "workflow_execution_id": uuid4(),
                },
                {"configurable": {}},
            )
            visit_counts = loaded["visit_counts"]
            step_results.append(
                StepResult(
                    step_index=i,
                    step_id="s0",
                    task=step_a.task,
                    output=output,
                    success=True,
                    error=None,
                    duration_ms=0,
                )
            )
            result, visit_counts = await self._run_route_cycle(
                steps=steps,
                step_results=step_results,
                visit_counts=visit_counts,
                client=client,
            )
            assert result["current_step_id"] == "s0"

        loaded = await load_workflow_step(
            {
                "workflow_steps": steps,
                "steps_by_id": {"s0": step_a, "s1": step_b},
                "current_step_id": "s0",
                "visit_counts": visit_counts,
                "workflow_execution_id": uuid4(),
            },
            {"configurable": {}},
        )
        visit_counts = loaded["visit_counts"]
        step_results.append(
            StepResult(
                step_index=2,
                step_id="s0",
                task=step_a.task,
                output="found it",
                success=True,
                error=None,
                duration_ms=0,
            )
        )
        result, visit_counts = await self._run_route_cycle(
            steps=steps,
            step_results=step_results,
            visit_counts=visit_counts,
            client=client,
        )

        assert result["current_step_id"] == "s1"
        assert result["current_step_id"] != "FAIL"
        assert result["workflow_step_results"][-1].branch_taken == "answer found"
        assert visit_counts["s0"] == 3
        assert after_route_branch(result) == "load_workflow_step"
