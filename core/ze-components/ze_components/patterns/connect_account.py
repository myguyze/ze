from __future__ import annotations

from ze_components.atoms import caption, error, primary, subheading, success
from ze_components.atoms.badge import Badge, badge
from ze_components.molecules import between, card
from ze_components.molecules.col import Col


def connect_account(
    id: str,
    provider: str,
    title: str,
    description: str,
    status: str = "not_connected",
    action_label: str = "Connect",
) -> Col:
    """Account connection card with status badge and optional connect button."""
    status_badge_fn = {"connected": success, "error": error}.get(status, badge)
    children: list = [
        between([subheading(title), status_badge_fn(status)]),  # type: ignore[operator]
        caption(description),
    ]
    if status != "connected":
        children.append(primary(action_label, f"connect:{provider}:{id}"))
    return card(children)
