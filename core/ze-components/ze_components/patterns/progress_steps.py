from __future__ import annotations

from ze_components.atoms import badge, error, info, spacer, subheading, success, text
from ze_components.molecules import center, col
from ze_components.molecules.col import Col

_STATUS_BADGE: dict[str, object] = {
    "done":    success,
    "active":  info,
    "error":   error,
}


def progress_steps(title: str, steps: list[dict]) -> Col:
    """Step tracker — done / active / pending steps with status badges."""
    rows: list = []
    for step in steps:
        badge_fn = _STATUS_BADGE.get(step["status"], badge)
        rows.append(center([badge_fn(step["status"]), text(step["label"])]))  # type: ignore[operator]
    return col([subheading(title), spacer("sm")] + rows)
