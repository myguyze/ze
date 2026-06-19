from __future__ import annotations

from ze_components.atoms import button, text
from ze_components.molecules import card, row
from ze_components.molecules.col import Col


def confirm_prompt(prompt: str, actions: list[dict]) -> Col:
    """Prompt with a row of action buttons. action.value is sent as the reply message."""
    buttons: list = [
        button(a["label"], a["value"], a.get("style", "secondary"))
        for a in actions
    ]
    return card([text(prompt), row(buttons)], gap="md")
