from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from ze_logging import bind_context, unbind_context


@contextmanager
def bound_turn_context(thread_id: str, *, agent: str | None = None) -> Iterator[None]:
    """Bind session-scoped log fields for one WebSocket turn."""
    bind_context(session_id=thread_id, agent=agent)
    try:
        yield
    finally:
        unbind_context()
