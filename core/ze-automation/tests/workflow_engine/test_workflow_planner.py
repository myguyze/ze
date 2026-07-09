"""Tests for WorkflowPlanner.extract_procedure."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock


from ze_automation.workflow.planner import WorkflowPlanner
from ze_automation.workflow.types import Branch, StepResult


def _make_step(task: str, success: bool = True, idx: int = 0) -> StepResult:
    return StepResult(
        step_index=idx,
        task=task,
        output="done" if success else "",
        success=success,
        error=None if success else "failed",
        duration_ms=0,
    )


def _make_planner(response: str) -> WorkflowPlanner:
    client = MagicMock()
    client.complete = AsyncMock(return_value=response)
    return WorkflowPlanner(openrouter_client=client)


class TestExtractProcedure:
    async def test_returns_procedure_from_valid_response(self):
        payload = json.dumps({
            "name": "Send prospecting emails",
            "trigger": "When reaching out to a new batch of prospects",
            "preconditions": ["Have a target list"],
            "steps": ["Research prospect", "Draft email", "Send"],
            "success_criteria": ["All emails delivered"],
        })
        planner = _make_planner(payload)

        steps = [_make_step("Research prospect"), _make_step("Draft email"), _make_step("Send")]
        result = await planner.extract_procedure("Outreach campaign", steps)

        assert result is not None
        assert result.name == "Send prospecting emails"
        assert result.trigger == "When reaching out to a new batch of prospects"
        assert len(result.steps) == 3

    async def test_returns_none_when_name_is_null(self):
        planner = _make_planner(json.dumps({"name": None}))
        steps = [_make_step("Do something specific")]
        result = await planner.extract_procedure("One-off task", steps)
        assert result is None

    async def test_returns_none_when_no_successful_steps(self):
        planner = _make_planner(json.dumps({"name": "whatever"}))
        steps = [_make_step("Failed step", success=False)]
        result = await planner.extract_procedure("Broken workflow", steps)
        assert result is None

    async def test_returns_none_on_llm_failure(self, mocker):
        mocker.patch("ze_automation.workflow.planner.log")
        client = MagicMock()
        client.complete = AsyncMock(side_effect=RuntimeError("LLM error"))
        planner = WorkflowPlanner(openrouter_client=client)
        steps = [_make_step("Do something")]
        result = await planner.extract_procedure("Some workflow", steps)
        assert result is None

    async def test_returns_none_on_invalid_json(self, mocker):
        mocker.patch("ze_automation.workflow.planner.log")
        planner = _make_planner("not json at all")
        steps = [_make_step("Step")]
        result = await planner.extract_procedure("Workflow", steps)
        assert result is None

    async def test_falls_back_to_step_tasks_when_steps_missing(self):
        payload = json.dumps({
            "name": "Research and report",
            "trigger": "When research is needed",
        })
        planner = _make_planner(payload)
        steps = [_make_step("Search the web", idx=0), _make_step("Write summary", idx=1)]
        result = await planner.extract_procedure("Research workflow", steps)

        assert result is not None
        assert result.steps == ["Search the web", "Write summary"]

    async def test_only_successful_steps_sent_to_llm(self):
        payload = json.dumps({"name": "Partial procedure", "trigger": "t", "steps": []})
        client = MagicMock()
        client.complete = AsyncMock(return_value=payload)
        planner = WorkflowPlanner(openrouter_client=client)

        steps = [
            _make_step("Step A", success=True, idx=0),
            _make_step("Step B", success=False, idx=1),
            _make_step("Step C", success=True, idx=2),
        ]
        await planner.extract_procedure("Mixed workflow", steps)

        prompt = client.complete.call_args[1]["messages"][0]["content"]
        assert "Step A" in prompt
        assert "Step B" not in prompt
        assert "Step C" in prompt


class TestPlan:
    async def test_parses_markdown_fenced_json_array(self):
        payload = json.dumps([
            {"task": "Send reminder", "agent_hint": "email", "intent": "create", "verify": None},
        ])
        planner = _make_planner(f"```json\n{payload}\n```")
        steps = await planner.plan("Remind João to water plants")
        assert len(steps) == 1
        assert steps[0].task == "Send reminder"
        assert steps[0].agent_hint == "email"

    async def test_plan_emits_branches_for_conditional_description(self):
        payload = json.dumps([
            {
                "task": "Check inbox for an invoice from Acme",
                "agent_hint": "email",
                "intent": "read",
                "verify": "inbox was checked",
                "id": "s0",
                "branches": [
                    {"condition": "invoice found", "to": "s1"},
                    {"condition": "no invoice found", "to": "s2"},
                ],
            },
            {"task": "Forward invoice to accounting", "id": "s1", "intent": "execute"},
            {"task": "Log that no invoice arrived", "id": "s2", "intent": "execute"},
        ])
        planner = _make_planner(payload)
        steps = await planner.plan(
            "Check my inbox for an Acme invoice; if one arrived forward it to accounting, otherwise log that none arrived."
        )

        assert any(s.branches for s in steps)
        assert steps[0].branches == [
            Branch(condition="invoice found", to="s1"),
            Branch(condition="no invoice found", to="s2"),
        ]
        assert steps[0].id == "s0"
        assert [s.id for s in steps] == ["s0", "s1", "s2"]

    async def test_plan_returns_empty_branches_for_linear_description(self):
        payload = json.dumps([
            {"task": "Fetch news headlines", "agent_hint": "news", "intent": "read"},
            {"task": "Summarize the headlines", "intent": "reason"},
            {"task": "Send the digest", "agent_hint": "email", "intent": "execute"},
        ])
        planner = _make_planner(payload)
        steps = await planner.plan("Fetch news, summarize it, and email me the digest.")

        assert len(steps) == 3
        assert all(s.branches == [] for s in steps)
        assert all(s.default_next is None for s in steps)
        assert [s.id for s in steps] == ["s0", "s1", "s2"]


class TestExtractSchedule:
    async def test_parses_markdown_fenced_json_object(self):
        payload = json.dumps({"cron": "0 8 * * 1"})
        planner = _make_planner(f"```json\n{payload}\n```")
        cron = await planner.extract_schedule("every Monday at 8am")
        assert cron == "0 8 * * 1"
