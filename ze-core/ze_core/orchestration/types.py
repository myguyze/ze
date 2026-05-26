from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ze_core.capability.types import GateDecision
from ze_core.memory.types import MemoryContext  # re-exported for AgentContext consumers


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None


@runtime_checkable
class ProgressReporter(Protocol):
    async def report(self, message: str) -> None: ...


@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    gate_decision: GateDecision = GateDecision.EXECUTE
    memory: MemoryContext = field(default_factory=MemoryContext)
    messages: list[dict] = field(default_factory=list)
    persona: dict = field(default_factory=dict)
    model: str | None = None
    reporter: ProgressReporter | None = None


@dataclass
class AgentResult:
    agent: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    memory_proposals: list = field(default_factory=list)
    contact_proposals: list = field(default_factory=list)
