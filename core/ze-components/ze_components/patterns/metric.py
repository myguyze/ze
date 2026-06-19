from __future__ import annotations

from ze_components.atoms import badge, heading, label, muted
from ze_components.molecules import card
from ze_components.molecules.col import Col


def metric(
    label_text: str,
    value: str,
    trend: str | None = None,
    note: str | None = None,
) -> Col:
    """Highlighted metric card — value (large), label, optional trend badge and note."""
    children: list = [heading(value), label(label_text)]
    if trend:
        children.append(badge(trend))
    if note:
        children.append(muted(note))
    return card(children)
