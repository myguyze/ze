from __future__ import annotations

from ze_automation.workflow.types import WorkflowStep

_COMPARED_FIELDS = (
    "task",
    "agent_hint",
    "verify",
    "intent",
    "branches",
    "default_next",
    "on_failure",
)


def _branches_value(step: WorkflowStep) -> list[tuple[str, str]]:
    return [(b.condition, b.to) for b in step.branches]


def _field_value(step: WorkflowStep, field_name: str) -> object:
    if field_name == "branches":
        return _branches_value(step)
    return getattr(step, field_name)


def build_change_summary(
    before: list[WorkflowStep], after: list[WorkflowStep], change_type: str
) -> str:
    if change_type == "created":
        return f"Workflow created with {len(after)} step(s)"

    before_by_id = {s.id: s for s in before}
    after_by_id = {s.id: s for s in after}

    clauses: list[str] = []

    for step_id, step in after_by_id.items():
        if step_id not in before_by_id:
            clauses.append(f"Step {step_id} added")

    for step_id in before_by_id:
        if step_id not in after_by_id:
            clauses.append(f"Step {step_id} removed")

    for step_id, after_step in after_by_id.items():
        before_step = before_by_id.get(step_id)
        if before_step is None:
            continue
        for field_name in _COMPARED_FIELDS:
            before_value = _field_value(before_step, field_name)
            after_value = _field_value(after_step, field_name)
            if before_value != after_value:
                clauses.append(
                    f"Step {step_id}: {field_name} {before_value} → {after_value}"
                )

    return "; ".join(clauses)
