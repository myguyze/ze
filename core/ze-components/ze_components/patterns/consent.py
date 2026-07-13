from __future__ import annotations

from ze_components.atoms import (
    caption,
    divider,
    label,
    primary,
    secondary,
    subheading,
    text,
)
from ze_components.molecules import card, col, row
from ze_components.molecules.col import Col


def consent(
    title: str,
    body: str,
    scopes: list[dict],
    accept_label: str = "Allow",
    reject_label: str = "Skip",
) -> Col:
    """Consent card with explicit scope list and accept/reject buttons."""
    scope_items: list = [
        col([label(s["label"]), caption(s["description"])], gap="none") for s in scopes
    ]
    return card(
        [
            subheading(title),
            text(body),
            divider(),
            *scope_items,
            row([primary(accept_label, "accept"), secondary(reject_label, "reject")]),
        ],
        gap="md",
    )
