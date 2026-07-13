from __future__ import annotations

from ze_components.atoms import primary, secondary, subheading
from ze_components.molecules import card, row
from ze_components.molecules.col import Col
from ze_components.organisms import table


def review(
    id: str,
    title: str,
    items: list[dict],
    approve_label: str = "Save",
    reject_label: str = "Edit",
) -> Col:
    """Review card — table of field/value pairs with approve and edit buttons."""
    rows = [[item["label"], item["value"]] for item in items]
    return card(
        [
            subheading(title),
            table(["Field", "Value"], rows),
            row(
                [
                    primary(approve_label, f"approve:{id}"),
                    secondary(reject_label, f"edit:{id}"),
                ]
            ),
        ],
        gap="md",
    )
