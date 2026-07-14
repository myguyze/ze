from __future__ import annotations

import re

from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.types import WorkflowStep

_TERMINAL_TARGETS = {"END", "FAIL"}
_SKIP_TO_PATTERN = re.compile(r"^skip_to:[a-zA-Z0-9_-]+$")


def validate_workflow_steps(steps: list[WorkflowStep]) -> None:
    """Raise WorkflowPlanError if the step graph is invalid."""
    step_ids = [s.id for s in steps]
    seen: set[str] = set()
    for step_id in step_ids:
        if step_id in seen:
            raise WorkflowPlanError(f"duplicate step id '{step_id}'")
        seen.add(step_id)

    valid_targets = seen | _TERMINAL_TARGETS
    for step in steps:
        if step.on_failure not in ("fail", "continue") and not _SKIP_TO_PATTERN.match(
            step.on_failure
        ):
            raise WorkflowPlanError(
                f"step '{step.id}' has invalid on_failure policy '{step.on_failure}'"
            )
        if step.on_failure.startswith("skip_to:"):
            target = step.on_failure.split(":", 1)[1]
            if target not in seen:
                raise WorkflowPlanError(
                    f"step '{step.id}' on_failure skip_to target '{target}' does not exist"
                )
        for branch in step.branches:
            if branch.to not in valid_targets:
                raise WorkflowPlanError(
                    f"step '{step.id}' branches to unknown step '{branch.to}'"
                )
        if step.default_next is not None and step.default_next not in valid_targets:
            raise WorkflowPlanError(
                f"step '{step.id}' default_next refers to unknown step '{step.default_next}'"
            )
