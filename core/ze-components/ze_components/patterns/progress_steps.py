from __future__ import annotations

from ze_components.organisms.steps import StepItem, Steps


def progress_steps(title: str, steps: list[dict]) -> Steps:
    """Step tracker — done / active / pending / error steps on a vertical rail."""
    return Steps(
        steps=[
            StepItem(
                label=step["label"],
                status=step["status"],
                note=step.get("note"),
            )
            for step in steps
        ],
        title=title,
    )
