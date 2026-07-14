import pytest

from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.types import Branch, WorkflowStep
from ze_automation.workflow.validation import validate_workflow_steps


def test_validate_accepts_valid_graph():
    steps = [
        WorkflowStep(task="a", id="s0", on_failure="continue"),
        WorkflowStep(task="b", id="s1", on_failure="skip_to:s0"),
    ]
    validate_workflow_steps(steps)


def test_validate_rejects_duplicate_ids():
    steps = [
        WorkflowStep(task="a", id="s0"),
        WorkflowStep(task="b", id="s0"),
    ]
    with pytest.raises(WorkflowPlanError, match="duplicate step id"):
        validate_workflow_steps(steps)


def test_validate_rejects_unknown_skip_to_target():
    steps = [WorkflowStep(task="a", id="s0", on_failure="skip_to:s9")]
    with pytest.raises(WorkflowPlanError, match="skip_to target"):
        validate_workflow_steps(steps)


def test_validate_rejects_dangling_branch():
    steps = [
        WorkflowStep(
            task="a",
            id="s0",
            branches=[Branch(condition="x", to="missing")],
        )
    ]
    with pytest.raises(WorkflowPlanError, match="branches to unknown step"):
        validate_workflow_steps(steps)


def test_validate_rejects_invalid_on_failure_policy():
    steps = [WorkflowStep(task="a", id="s0", on_failure="abort")]
    with pytest.raises(WorkflowPlanError, match="invalid on_failure"):
        validate_workflow_steps(steps)
