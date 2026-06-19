from __future__ import annotations

from ze_components.atoms import badge, caption, error, info, subheading, success, text
from ze_components.molecules import center, col
from ze_components.molecules.col import Col

_STATUS_BADGE: dict[str, object] = {
    "done":    success,
    "active":  info,
    "error":   error,
}


def list_items(items: list[dict], title: str | None = None) -> Col:
    """Vertical list with optional status badges and subtitles per item."""
    rows: list = []
    for item in items:
        inner: list = [text(item["text"])]
        if item.get("subtext"):
            inner.append(caption(item["subtext"]))
        status = item.get("status")
        if status:
            badge_fn = _STATUS_BADGE.get(status, badge)
            rows.append(center([badge_fn(status), col(inner, gap="none")]))  # type: ignore[operator]
        else:
            rows.append(col(inner, gap="none"))
    children: list = ([subheading(title)] if title else []) + rows
    return col(children)
