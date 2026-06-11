from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, runtime_checkable

from typing_extensions import Protocol

if TYPE_CHECKING:
    from ze_agents.types import AgentContext, ToolCall


@dataclass
class ToolStartEvent:
    tool_name: str
    args: dict[str, Any]
    ctx: "AgentContext"
    iteration: int  # loop iteration (0-indexed); -1 for direct call_tool outside a loop


@dataclass
class ToolEndEvent:
    tool_name: str
    tool_call: "ToolCall"
    ctx: "AgentContext"
    iteration: int


@dataclass
class LoopStartEvent:
    agent_name: str
    ctx: "AgentContext"


@dataclass
class LoopEndEvent:
    agent_name: str
    ctx: "AgentContext"
    tool_calls: "list[ToolCall]"
    iterations_used: int


@runtime_checkable
class HarnessHook(Protocol):
    """Extension point for cross-cutting concerns in the agent execution loop.

    All methods have default no-op implementations via BaseHarnessHook.
    Hooks self-filter by agent using event.ctx.intent or event.tool_name.
    """

    async def on_tool_start(self, event: ToolStartEvent) -> dict[str, Any] | None:
        """Called before a tool executes.

        Return a modified args dict to replace the original args.
        Return None to use args unchanged.
        Raise HookAbort to skip this tool call entirely.
        Raise AgentAbortedError to stop the whole loop.
        """
        ...

    async def on_tool_end(self, event: ToolEndEvent) -> None:
        """Called after a tool executes (success or error). Cannot modify the result."""
        ...

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        """Called once when agentic_loop begins, before the first LLM call."""
        ...

    async def on_loop_end(self, event: LoopEndEvent) -> None:
        """Called once when agentic_loop returns (text response or max iterations)."""
        ...


class BaseHarnessHook:
    """Mixin with default no-op implementations. Inherit to override only what you need."""

    async def on_tool_start(self, event: ToolStartEvent) -> dict[str, Any] | None:
        return None

    async def on_tool_end(self, event: ToolEndEvent) -> None:
        pass

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        pass

    async def on_loop_end(self, event: LoopEndEvent) -> None:
        pass


# ── Registry ──────────────────────────────────────────────────────────────────

_hooks: list[HarnessHook] = []


def register_hook(hook: HarnessHook) -> None:
    """Register a global hook. Called once at application startup."""
    _hooks.append(hook)


def get_hooks() -> list[HarnessHook]:
    """Return all registered hooks in registration order."""
    return list(_hooks)


def clear_hooks() -> None:
    """Remove all registered hooks. Intended for tests only."""
    _hooks.clear()
