from __future__ import annotations

from ze_automation.workflow.types import Branch, StepResult, WorkflowStep


def test_workflow_step_defaults_reproduce_todays_shape():
    step = WorkflowStep(task="Send reminder")

    assert step.agent_hint is None
    assert step.verify is None
    assert step.intent == "execute"
    assert step.id == ""
    assert step.branches == []
    assert step.default_next is None


def test_workflow_step_accepts_branches():
    step = WorkflowStep(
        task="Check invoice",
        id="s1",
        branches=[Branch(condition="invoice found", to="s2")],
        default_next="s3",
    )

    assert step.id == "s1"
    assert step.branches == [Branch(condition="invoice found", to="s2")]
    assert step.default_next == "s3"


def test_step_result_defaults_reproduce_todays_shape():
    result = StepResult(
        step_index=0,
        task="Send reminder",
        output="done",
        success=True,
        error=None,
        duration_ms=10,
    )

    assert result.step_id == ""
    assert result.branch_taken is None


def test_step_result_accepts_branch_taken():
    result = StepResult(
        step_index=0,
        task="Check invoice",
        output="found",
        success=True,
        error=None,
        duration_ms=10,
        step_id="s1",
        branch_taken="invoice found",
    )

    assert result.step_id == "s1"
    assert result.branch_taken == "invoice found"
