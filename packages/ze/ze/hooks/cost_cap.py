"""Tool-call cap hook — aborts a tool call when the per-turn limit is exceeded.

Prevents runaway agentic loops from consuming unbounded LLM credits.
The counter resets at the start of each agentic_loop invocation, so the
cap applies per turn (not per session lifetime).
"""
from __future__ import annotations

from ze_core.errors import HookAbort
from ze_core.logging import get_logger
from ze_core.orchestration.hooks import BaseHarnessHook, LoopStartEvent, ToolStartEvent

log = get_logger(__name__)


class ToolCallCapHook(BaseHarnessHook):
    """Raise HookAbort when a turn exceeds max_tool_calls tool executions."""

    def __init__(self, max_tool_calls: int = 20) -> None:
        self._max = max_tool_calls
        self._counts: dict[str, int] = {}

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        self._counts[event.ctx.session_id] = 0

    async def on_tool_start(self, event: ToolStartEvent) -> None:
        session_id = event.ctx.session_id
        count = self._counts.get(session_id, 0) + 1
        self._counts[session_id] = count
        if count > self._max:
            log.warning(
                "tool_call_cap_exceeded",
                session_id=session_id,
                tool=event.tool_name,
                count=count,
                max=self._max,
            )
            raise HookAbort(
                event.tool_name,
                reason=f"tool-call cap exceeded ({count}/{self._max})",
            )
