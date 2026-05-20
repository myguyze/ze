from dataclasses import dataclass, field
from typing import Any

from ze.capability.types import GateDecision
from ze.memory.types import MemoryContext


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
    memory: MemoryContext = field(default_factory=MemoryContext)
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)  # history + current user message
    model: str | None = None    # None → agent falls back to its config default


@dataclass
class AgentResult:
    agent: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    memory_proposals: list = field(default_factory=list)  # list[UserFact], populated by agents
