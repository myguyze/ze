"""Ze BaseAgent — extends ze-core with persona, progress, and OpenRouter wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from ze.agents.identity import build_identity_block
from ze.agents.types import AgentContext, AgentResult, ToolCall
from ze_core.orchestration.base_agent import BaseAgent as _CoreBaseAgent
from ze_core.orchestration.base_agent import _truncate_messages

if TYPE_CHECKING:
    from ze.settings import Settings


class BaseAgent(_CoreBaseAgent):
    """Ze application agent base: ze-core execution + Ze system prompt composition."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        from ze.logging import get_logger
        self._log = get_logger(__name__)

    async def call_tool(self, name: str, ctx: AgentContext, **kwargs) -> ToolCall:
        """Unwrap legacy Ze tools that still return a nested ToolCall."""
        tc = await super().call_tool(name, ctx, **kwargs)
        inner = tc.result
        if isinstance(inner, ToolCall):
            return ToolCall(
                tool_name=tc.tool_name,
                args=tc.args,
                result=inner.result,
                duration_ms=tc.duration_ms,
                success=tc.success and inner.success,
                error=inner.error or tc.error,
                is_draft=tc.is_draft,
            )
        return tc

    def _model(self, ctx: AgentContext | None = None) -> str:
        if ctx is not None and ctx.model is not None:
            return ctx.model
        return self.model

    def _timeout(self) -> int:
        return int(self.timeout)

    def _format_memory(self, ctx: AgentContext) -> str:
        lines = [f"- {f.key}: {f.value}" for f in ctx.memory.facts]
        return "\n".join(lines) if lines else "(none)"

    def _format_contacts(self, ctx: AgentContext) -> str:
        lines = []
        for p in ctx.contacts.people:
            line = f"- {p.name}: {p.relationship_to_user}"
            if p.notes:
                line += f" ({p.notes})"
            lines.append(line)
        return "\n".join(lines)

    def _build_system_prompt(
        self,
        agent_instructions: str,
        ctx: AgentContext,
        **extra: str,
    ) -> str:
        identity = build_identity_block(
            ctx.persona if ctx.persona else self._settings.active_profile(),
            self._format_memory(ctx),
            profile=ctx.memory.profile,
            contacts_context=self._format_contacts(ctx),
        )
        rendered = agent_instructions.format(**extra) if extra else agent_instructions
        return f"{identity}\n\n{rendered}"


__all__ = ["BaseAgent", "_truncate_messages"]
