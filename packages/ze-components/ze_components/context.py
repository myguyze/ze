from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict
from typing import Any

_pending: ContextVar[list[dict[str, Any]]] = ContextVar("ze_components_pending")


def begin_collection() -> object:
    """Reset the pending list for the current async context. Returns a reset token."""
    return _pending.set([])


def append(component: object) -> None:
    """Append a rendered component dict. No-ops if called outside a collection context."""
    try:
        current = _pending.get()
    except LookupError:
        return
    _pending.set(current + [asdict(component)])  # type: ignore[arg-type]


def collect_and_reset(token: object) -> list[dict[str, Any]]:
    """Drain accumulated components, restore prior context state, and return the list."""
    try:
        result = list(_pending.get())
    except LookupError:
        result = []
    _pending.reset(token)  # type: ignore[arg-type]
    return result
