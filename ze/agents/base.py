import time
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ze.agents.identity import build_identity_block
from ze.agents.tool import ToolAccess, get_tool
from ze.agents.types import AgentContext, AgentResult, ToolCall
from ze.capability.types import GateDecision
from ze.errors import ToolBlockedError
from ze.logging import get_logger
from ze.settings import Settings


class BaseAgent(ABC):
    name: str           # set by subclass as a class attribute
    tools: list[str] = []  # names of tools this agent may call

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._log = get_logger(__name__)

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent and return a complete result."""

    @abstractmethod
    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """Stream response tokens."""
        raise NotImplementedError
        yield  # make mypy happy

    # ── Lifecycle (optional override) ─────────────────────────────────────────

    async def startup(self) -> None:
        """Called once at app startup after DI wiring. Override for warmup."""

    async def shutdown(self) -> None:
        """Called during app shutdown. Override for cleanup."""

    # ── Tool execution ────────────────────────────────────────────────────────

    async def call_tool(self, name: str, ctx: AgentContext, **kwargs) -> ToolCall:
        """Execute a registered tool with capability enforcement.

        READ tools execute in any gate state.
        WRITE tools are suppressed and return a draft ToolCall when gate is DRAFT.
        Any tool raises ToolBlockedError when gate is BLOCKED.
        """
        spec = get_tool(name)

        if ctx.gate_decision == GateDecision.BLOCKED:
            raise ToolBlockedError(
                f"Tool {name!r} is blocked by the capability gate"
            )

        if spec.access == ToolAccess.WRITE and ctx.gate_decision == GateDecision.DRAFT:
            self._log.info("tool_suppressed_draft", tool=name, agent=self.name)
            return ToolCall(
                tool_name=name,
                args=kwargs,
                result=None,
                duration_ms=0,
                success=False,
                error="suppressed: draft mode",
                is_draft=True,
            )

        self._log.debug("tool_start", tool=name, agent=self.name, access=spec.access.value)
        start = time.monotonic()
        try:
            result = await spec.fn(**kwargs)
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._log.warning("tool_error", tool=name, agent=self.name, error=str(exc))
            return ToolCall(
                tool_name=name,
                args=kwargs,
                result=None,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )

        self._log.info(
            "tool_complete",
            tool=name,
            agent=self.name,
            success=result.success,
            duration_ms=result.duration_ms,
        )
        return result

    # ── Config helpers ────────────────────────────────────────────────────────

    def _model(self, ctx: AgentContext | None = None) -> str:
        if ctx is not None and ctx.model is not None:
            return ctx.model
        return self._settings.agent_configs.get(self.name, {}).get(
            "model", "anthropic/claude-sonnet-4-5"
        )

    def _timeout(self) -> int:
        return int(
            self._settings.agent_configs.get(self.name, {}).get("timeout", 30)
        )

    def _format_memory(self, ctx: AgentContext) -> str:
        lines = [f"- {f.key}: {f.value}" for f in ctx.memory.facts]
        return "\n".join(lines) if lines else "(none)"

    def _build_system_prompt(
        self,
        agent_instructions: str,
        ctx: AgentContext,
        **extra: str,
    ) -> str:
        """Compose the full system prompt: shared identity block + agent instructions."""
        identity = build_identity_block(
            self._settings.persona_config,
            self._format_memory(ctx),
            profile=ctx.memory.profile,
        )
        rendered = agent_instructions.format(**extra) if extra else agent_instructions
        return f"{identity}\n\n{rendered}"
