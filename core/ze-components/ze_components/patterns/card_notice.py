from __future__ import annotations

from ze_components.atoms import subheading, text
from ze_components.molecules import card, section
from ze_components.molecules.col import Col


def card_notice(body: str, title: str | None = None, style: str = "info") -> Col:
    """Highlighted notice card. style: 'info' | 'warning' | 'success' | 'error'."""
    variant_fn = section if style in ("warning", "success", "error") else card
    children: list = ([subheading(title)] if title else []) + [text(body)]
    return variant_fn(children)
