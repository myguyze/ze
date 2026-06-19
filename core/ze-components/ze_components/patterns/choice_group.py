from __future__ import annotations

from ze_components.atoms import caption, info, primary, spacer, subheading, text
from ze_components.molecules import between, card, col
from ze_components.molecules.col import Col


def choice_group(
    title: str,
    options: list[dict],
    description: str | None = None,
    submit_label: str = "Continue",
) -> Col:
    """Choice group for interactive selection — one primary button per option."""
    children: list = [subheading(title)]
    if description:
        children.append(caption(description))
    children.append(spacer("sm"))
    for opt in options:
        inner: list = [text(opt["label"])]
        if opt.get("description"):
            inner.append(caption(opt["description"]))
        row_items: list = [col(inner, gap="none")]
        if opt.get("recommended"):
            row_items.append(info("recommended"))
        children.append(between([col(row_items), primary(submit_label, opt["id"])]))
    return card(children)
