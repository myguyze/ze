from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


# ── Capability types ──────────────────────────────────────────────────────────

class Mode(str, Enum):
    AUTONOMOUS = "autonomous"
    CONFIRM    = "confirm"
    DRAFT_ONLY = "draft_only"
    DISABLED   = "disabled"


class GateDecision(str, Enum):
    EXECUTE            = "execute"
    DRAFT              = "draft"
    AWAIT_CONFIRMATION = "confirm"
    BLOCKED            = "blocked"


# ── Orchestration types ───────────────────────────────────────────────────────

@dataclass
class AbortToken:
    """Async abort signal for agentic loops. Set from outside; checked per iteration."""
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str | None = None

    def abort(self, reason: str | None = None) -> None:
        """Signal the running loop to stop after the current tool call completes."""
        self.reason = reason
        self._event.set()

    @property
    def is_set(self) -> bool:
        return self._event.is_set()


class IdentityBuilder(Protocol):
    """Callable that renders the persona/memory preamble injected into agent prompts."""

    def __call__(
        self,
        persona: dict,
        memory_context: str,
        *,
        profile: Any,
        contacts_context: str,
    ) -> str: ...


@dataclass
class ToolCall:
    tool_name: str
    args: dict[str, Any]
    result: Any
    duration_ms: int
    success: bool
    error: str | None = None
    is_draft: bool = False


@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    gate_decision: GateDecision = GateDecision.EXECUTE
    memory: Any = None
    contacts: Any = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    persona: dict = field(default_factory=dict)
    model: str | None = None
    reporter: Any = field(default=None, repr=False)  # ProgressReporter | None
    # identity_builder is runtime-only (a callable); always None in stored state.
    # Never checkpoint a context where this is set — the serde test enforces that.
    identity_builder: IdentityBuilder | None = field(default=None, repr=False)
    # abort_token is runtime-only; never checkpoint a context where this is set.
    abort_token: AbortToken | None = field(default=None, repr=False)
    # memory_store is runtime-only; set by GoalExecutor for direct agent invocations
    # that bypass the fetch_context graph node. Never checkpoint.
    memory_store: Any = field(default=None, repr=False)
    # embed_fn is runtime-only; injected by the container so BaseAgent can compute
    # embeddings without importing ze-core. Never checkpoint.
    embed_fn: Callable[[str], Any] | None = field(default=None, repr=False)
    # extensions must hold only msgpack-serializable primitives so stored contexts
    # can be checkpointed. Use identity_builder for callable injection instead.
    extensions: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    memory_proposals: list = field(default_factory=list)
    contact_proposals: list = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
