from dataclasses import dataclass, field
from typing import Any

from ze.memory.types import MemoryContext


@dataclass
class ToolCall:
    tool_name: str
    args: dict[str, Any]
    result: Any
    duration_ms: int
    success: bool
    error: str | None = None


@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    memory: MemoryContext = field(default_factory=MemoryContext)
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AgentResult:
    agent: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    memory_proposals: list = field(default_factory=list)  # list[UserFact], populated by agents
