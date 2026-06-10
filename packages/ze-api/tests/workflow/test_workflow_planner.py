"""Tests for WorkflowPlanner.extract_procedure."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.workflow.planner import WorkflowPlanner
from ze_personal.workflow.types import StepResult


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
        mocker.patch("ze_personal.workflow.planner.log")
        client = MagicMock()
        client.complete = AsyncMock(side_effect=RuntimeError("LLM error"))
        planner = WorkflowPlanner(openrouter_client=client)
        steps = [_make_step("Do something")]
        result = await planner.extract_procedure("Some workflow", steps)
        assert result is None

    async def test_returns_none_on_invalid_json(self, mocker):
        mocker.patch("ze_personal.workflow.planner.log")
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
