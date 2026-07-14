import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_agents.types import AgentResult, ToolCall
from ze_automation.workflow.types import Branch, StepResult, WorkflowStep
from ze_personal.graph.workflow import (
    _resolve_step_output,
    _resolve_verify_model,
    after_handle_step_failure,
    after_route_branch,
    after_verify_step,
    handle_step_failure,
    load_workflow_step,
    retry_step,
    route_branch,
    verify_step,
    workflow_cancelled,
    workflow_failed,
    workflow_synthesize,
)


def _make_store() -> MagicMock:
    store = MagicMock()
    store.record_step = AsyncMock()
    return store


class TestResolveVerifyModel:
    def test_no_settings_returns_declared_default(self):
        config = {"configurable": {}}
        assert _resolve_verify_model(config) == "anthropic/claude-haiku-4-5"

    def test_models_override_pins_workflow_verify(self):
        config = {
            "configurable": {
                "settings": {
                    "models": {
                        "default": "fleet-default",
                        "overrides": {"workflow_verify": "pinned-model"},
                    }
                }
            }
        }
        assert _resolve_verify_model(config) == "pinned-model"


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
async def test_verify_step_records_duration_from_load_workflow_step_start():
    store = _make_store()
    config = {
        "configurable": {
            "workflow_store": store,
            "openrouter_client": MagicMock(),
        }
    }
    step = WorkflowStep(task="search news", intent="read", id="s0")
    loaded = await load_workflow_step(
        {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "current_step_id": "s0",
            "workflow_execution_id": uuid4(),
        },
        {"configurable": {}},
    )
    state = {
        "workflow_steps": [step],
        "steps_by_id": {"s0": step},
        "current_step_id": "s0",
        "step_started_at": loaded["step_started_at"],
        "workflow_execution_id": uuid4(),
        "workflow_step_results": [],
        "agent_result": None,
        "subtask_results": [AgentResult(agent="news", response="article summary")],
    }

    result = await verify_step(state, config)

    assert result["workflow_step_results"][0].duration_ms >= 0


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
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="Check invoice",
                    output="found an invoice",
                    success=True,
                    error=None,
                    duration_ms=0,
                )
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
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="Fetch news",
                    output="headlines",
                    success=True,
                    error=None,
                    duration_ms=0,
                )
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
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="Fetch news",
                    output="headlines",
                    success=True,
                    error=None,
                    duration_ms=0,
                )
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
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
        state = {
            "workflow_steps": steps,
            "steps_by_id": steps_by_id,
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="Send digest",
                    output="done",
                    success=True,
                    error=None,
                    duration_ms=0,
                )
            ],
            "workflow_execution_id": uuid4(),
        }

        result = await route_branch(state, config)

        assert result["current_step_id"] == "END"
        assert after_route_branch(result) == "workflow_synthesize"


class TestFailurePrecedesRouting:
    async def test_failed_step_routes_to_workflow_failed_and_never_reaches_route_branch(
        self,
    ):
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
        assert after_verify_step(result) == "handle_step_failure"
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
        failed_call = ToolCall(
            tool_name="send_email",
            args={},
            result=None,
            duration_ms=0,
            success=False,
            error="SMTP error",
        )
        state = {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "current_step_id": "s0",
            "workflow_execution_id": uuid4(),
            "workflow_step_results": [],
            "agent_result": AgentResult(
                agent="email", response="sent", tool_calls=[failed_call]
            ),
            "subtask_results": [],
        }

        result = await verify_step(state, config)

        assert result["workflow_step_results"][-1].success is False
        assert after_verify_step(result) == "handle_step_failure"


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
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
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

        failed = await workflow_failed(
            result, {"configurable": {"workflow_store": _make_store()}}
        )
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


class TestLegacyWorkflowExecution:
    def _legacy_linear_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep(task="Fetch news", agent_hint="news", intent="read", id="s0"),
            WorkflowStep(task="Summarize", intent="reason", id="s1"),
            WorkflowStep(task="Send digest", intent="execute", id="s2"),
        ]

    async def _run_linear_step(
        self,
        *,
        steps: list[WorkflowStep],
        step_id: str,
        output: str,
        step_results: list[StepResult],
        visit_counts: dict[str, int],
        client: MagicMock,
    ) -> tuple[dict, list[StepResult], dict[str, int]]:
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": client}
        }
        execution_id = uuid4()

        loaded = await load_workflow_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": step_id,
                "visit_counts": visit_counts,
                "workflow_execution_id": execution_id,
            },
            {"configurable": {}},
        )
        visit_counts = loaded["visit_counts"]

        verified = await verify_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": step_id,
                "workflow_execution_id": execution_id,
                "workflow_step_results": step_results,
                "agent_result": AgentResult(agent="news", response=output),
                "subtask_results": [],
            },
            config,
        )
        step_results = list(verified["workflow_step_results"])
        assert after_verify_step(verified) == "route_branch"

        routed = await route_branch(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "workflow_step_results": step_results,
                "workflow_execution_id": execution_id,
                "visit_counts": visit_counts,
            },
            config,
        )
        return routed, step_results, dict(routed.get("visit_counts") or visit_counts)

    async def test_linear_legacy_run_executes_every_step_in_original_order(self):
        steps = self._legacy_linear_steps()
        step_results: list[StepResult] = []
        visit_counts: dict[str, int] = {}
        client = MagicMock()
        client.complete = AsyncMock()

        for step_id, output in [("s0", "headlines"), ("s1", "summary"), ("s2", "sent")]:
            routed, step_results, visit_counts = await self._run_linear_step(
                steps=steps,
                step_id=step_id,
                output=output,
                step_results=step_results,
                visit_counts=visit_counts,
                client=client,
            )
            if step_id != "s2":
                assert routed["current_step_id"] == {"s0": "s1", "s1": "s2"}[step_id]
                assert after_route_branch(routed) == "load_workflow_step"
            else:
                assert routed["current_step_id"] == "END"
                assert after_route_branch(routed) == "workflow_synthesize"

        assert [r.step_id for r in step_results] == ["s0", "s1", "s2"]
        assert all(r.branch_taken is None for r in step_results)
        assert all(r.success for r in step_results)
        client.complete.assert_not_called()

    async def test_failed_legacy_step_fails_whole_run_without_retry(self):
        steps = self._legacy_linear_steps()
        steps_by_id = {s.id: s for s in steps}
        store = _make_store()
        config = {
            "configurable": {"workflow_store": store, "openrouter_client": MagicMock()}
        }
        execution_id = uuid4()
        visit_counts: dict[str, int] = {}

        loaded = await load_workflow_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": "s0",
                "visit_counts": visit_counts,
                "workflow_execution_id": execution_id,
            },
            {"configurable": {}},
        )
        visit_counts = loaded["visit_counts"]

        first = await verify_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": "s0",
                "workflow_execution_id": execution_id,
                "workflow_step_results": [],
                "agent_result": AgentResult(agent="news", response="headlines"),
                "subtask_results": [],
            },
            config,
        )
        step_results = list(first["workflow_step_results"])
        assert after_verify_step(first) == "route_branch"

        routed = await route_branch(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "workflow_step_results": step_results,
                "workflow_execution_id": execution_id,
                "visit_counts": visit_counts,
            },
            config,
        )
        assert routed["current_step_id"] == "s1"
        visit_counts = dict(routed.get("visit_counts") or visit_counts)

        loaded = await load_workflow_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": "s1",
                "visit_counts": visit_counts,
                "workflow_execution_id": execution_id,
            },
            {"configurable": {}},
        )
        visit_counts = loaded["visit_counts"]

        failed = await verify_step(
            {
                "workflow_steps": steps,
                "steps_by_id": steps_by_id,
                "current_step_id": "s1",
                "workflow_execution_id": execution_id,
                "workflow_step_results": step_results,
                "agent_result": AgentResult(agent="research", response=""),
                "subtask_results": [],
            },
            config,
        )

        assert failed["workflow_step_results"][-1].success is False
        assert failed["workflow_step_results"][-1].step_id == "s1"
        assert after_verify_step(failed) == "handle_step_failure"
        assert len(failed["workflow_step_results"]) == 2
        assert [r.step_id for r in failed["workflow_step_results"]] == ["s0", "s1"]


class TestOnFailurePolicies:
    async def test_continue_policy_routes_to_next_step(self):
        step_a = WorkflowStep(task="monitor", id="s0", on_failure="continue")
        step_b = WorkflowStep(task="report", id="s1")
        steps = [step_a, step_b]
        state = {
            "workflow_steps": steps,
            "steps_by_id": {s.id: s for s in steps},
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task=step_a.task,
                    output="",
                    success=False,
                    error="nothing found",
                    duration_ms=0,
                )
            ],
        }
        result = await handle_step_failure(state, {"configurable": {}})
        assert result["current_step_id"] == "s1"
        assert after_handle_step_failure(result) == "load_workflow_step"

    async def test_skip_to_policy_routes_to_target(self):
        step_a = WorkflowStep(task="monitor", id="s0", on_failure="skip_to:s2")
        step_b = WorkflowStep(task="skipped", id="s1")
        step_c = WorkflowStep(task="report", id="s2")
        steps = [step_a, step_b, step_c]
        state = {
            "workflow_steps": steps,
            "steps_by_id": {s.id: s for s in steps},
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task=step_a.task,
                    output="",
                    success=False,
                    error="failed",
                    duration_ms=0,
                )
            ],
        }
        result = await handle_step_failure(state, {"configurable": {}})
        assert result["current_step_id"] == "s2"

    async def test_default_fail_policy_routes_to_workflow_failed(self):
        step = WorkflowStep(task="critical", id="s0")
        state = {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task=step.task,
                    output="",
                    success=False,
                    error="boom",
                    duration_ms=0,
                )
            ],
        }
        result = await handle_step_failure(state, {"configurable": {}})
        assert result["current_step_id"] == "FAIL"
        assert after_handle_step_failure(result) == "workflow_failed"

    async def test_all_continue_failures_mark_run_failed(self):
        store = _make_store()
        store.finish_execution = AsyncMock()
        client = MagicMock()
        client.complete = AsyncMock(return_value="all failed summary")
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        step_results = [
            StepResult(
                step_index=0,
                step_id="s0",
                task="a",
                output="",
                success=False,
                error="fail a",
                duration_ms=0,
            ),
            StepResult(
                step_index=1,
                step_id="s1",
                task="b",
                output="",
                success=False,
                error="fail b",
                duration_ms=0,
            ),
        ]
        state = {
            "workflow_step_results": step_results,
            "workflow_execution_id": uuid4(),
        }
        result = await workflow_synthesize(state, config)
        assert "Workflow failed" in result["final_response"]
        store.finish_execution.assert_called_once()
        assert store.finish_execution.call_args.args[1] == "failed"


class TestPartialSynthesis:
    async def test_workflow_failed_includes_summary_when_prior_steps_succeeded(self):
        store = _make_store()
        store.finish_execution = AsyncMock()
        client = MagicMock()
        client.complete = AsyncMock(return_value="partial output summary")
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        execution_id = uuid4()
        state = {
            "workflow_execution_id": execution_id,
            "workflow_steps": [
                WorkflowStep(task="research", id="s0"),
                WorkflowStep(task="send", id="s1"),
            ],
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="research",
                    output="findings",
                    success=True,
                    error=None,
                    duration_ms=10,
                ),
                StepResult(
                    step_index=1,
                    step_id="s1",
                    task="send",
                    output="",
                    success=False,
                    error="smtp down",
                    duration_ms=5,
                ),
            ],
        }
        result = await workflow_failed(state, config)
        assert "partial output summary" in result["final_response"]
        store.finish_execution.assert_called_once()
        call = store.finish_execution.call_args
        assert call.args[0] == execution_id
        assert call.args[1] == "failed"
        assert call.kwargs["summary"] == "partial output summary"

    async def test_workflow_failed_without_successes_skips_synthesis(self):
        store = _make_store()
        store.finish_execution = AsyncMock()
        client = MagicMock()
        client.complete = AsyncMock()
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        state = {
            "workflow_execution_id": uuid4(),
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="only",
                    output="",
                    success=False,
                    error="failed immediately",
                    duration_ms=0,
                )
            ],
        }
        await workflow_failed(state, config)
        client.complete.assert_not_called()


class TestRetryRouting:
    async def test_transient_failure_routes_to_retry_step(self):
        state = {
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="fetch",
                    output="",
                    success=False,
                    error="Request timeout after 30s",
                    duration_ms=0,
                    attempt_count=1,
                )
            ],
            "step_attempt": 1,
        }
        assert after_verify_step(state) == "retry_step"

    async def test_retry_step_increments_attempt_and_strips_failed_result(self):
        state = {
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="fetch",
                    output="",
                    success=False,
                    error="503 service unavailable",
                    duration_ms=0,
                )
            ],
            "step_attempt": 1,
        }
        with patch("ze_personal.graph.workflow.asyncio.sleep", new=AsyncMock()):
            result = await retry_step(state, {"configurable": {}})
        assert result["step_attempt"] == 2
        assert result["from_retry"] is True
        assert result["workflow_step_results"] == []

    async def test_exhausted_retries_route_to_handle_step_failure(self):
        state = {
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="fetch",
                    output="",
                    success=False,
                    error="503 service unavailable",
                    duration_ms=0,
                    attempt_count=3,
                )
            ],
            "step_attempt": 3,
        }
        assert after_verify_step(state) == "handle_step_failure"


class TestNoResultsVerify:
    async def test_no_results_records_success(self):
        store = _make_store()
        client = MagicMock()
        client.complete = AsyncMock(
            return_value=json.dumps(
                {"pass": True, "no_results": True, "reason": "No new items found"}
            )
        )
        config = {"configurable": {"workflow_store": store, "openrouter_client": client}}
        step = WorkflowStep(
            task="Check for news",
            id="s0",
            verify="Empty result is valid if check ran",
        )
        state = {
            "workflow_steps": [step],
            "steps_by_id": {"s0": step},
            "current_step_id": "s0",
            "workflow_execution_id": uuid4(),
            "workflow_step_results": [],
            "agent_result": AgentResult(agent="news", response="checked, nothing new"),
            "subtask_results": [],
            "step_attempt": 1,
        }
        result = await verify_step(state, config)
        last = result["workflow_step_results"][-1]
        assert last.success is True
        assert last.no_results is True
        assert after_verify_step(result) == "route_branch"


class TestCancellation:
    async def test_workflow_cancelled_persists_cancelled_status(self):
        store = _make_store()
        store.finish_execution = AsyncMock()
        execution_id = uuid4()
        state = {
            "workflow_execution_id": execution_id,
            "workflow_step_results": [
                StepResult(
                    step_index=0,
                    step_id="s0",
                    task="long task",
                    output="partial",
                    success=True,
                    error=None,
                    duration_ms=100,
                )
            ],
        }
        result = await workflow_cancelled(state, {"configurable": {"workflow_store": store}})
        assert result["final_response"] == "Workflow run cancelled."
        store.finish_execution.assert_called_once_with(
            execution_id, "cancelled", summary=store.finish_execution.call_args.kwargs["summary"]
        )

    async def test_load_workflow_step_routes_to_cancelled_when_flagged(self):
        scheduler = MagicMock()
        scheduler.is_cancelled = MagicMock(return_value=True)
        execution_id = uuid4()
        step = WorkflowStep(task="work", id="s0")
        result = await load_workflow_step(
            {
                "workflow_steps": [step],
                "steps_by_id": {"s0": step},
                "current_step_id": "s0",
                "workflow_execution_id": execution_id,
            },
            {"configurable": {"workflow_scheduler": scheduler}},
        )
        assert result["current_step_id"] == "CANCELLED"
        assert after_route_branch(result) == "workflow_cancelled"
