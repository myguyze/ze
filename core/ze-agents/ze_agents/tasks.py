from __future__ import annotations

import asyncio
from typing import Any, Coroutine

from ze_logging import get_logger

_log = get_logger(__name__)


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, label: str) -> asyncio.Task:
    """Schedule a coroutine as a background task and log any exception at error level."""
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: _on_done(t, label))
    return task


def _on_done(task: asyncio.Task, label: str) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _log.error("background_task_failed", task=label, error=str(exc))
