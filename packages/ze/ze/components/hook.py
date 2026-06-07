from __future__ import annotations

from ze_components import context as _ctx
from ze_core.orchestration.hooks import BaseHarnessHook, LoopEndEvent, LoopStartEvent


class ComponentCollectionHook(BaseHarnessHook):
    """Brackets each agent loop to collect render_tool component descriptors."""

    def __init__(self) -> None:
        self._tokens: dict[str, object] = {}
        self._results: dict[str, list[dict]] = {}

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        token = _ctx.begin_collection()
        self._tokens[event.ctx.session_id] = token

    async def on_loop_end(self, event: LoopEndEvent) -> None:
        token = self._tokens.pop(event.ctx.session_id, None)
        if token is None:
            return
        self._results[event.ctx.session_id] = _ctx.collect_and_reset(token)

    def pop_components(self, session_id: str) -> list[dict]:
        """Read and clear collected components for a session. Returns [] if none."""
        return self._results.pop(session_id, [])
