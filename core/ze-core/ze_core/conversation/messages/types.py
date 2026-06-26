from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

MessageRole = Literal["user", "assistant"]


@dataclass
class Message:
    id: UUID
    role: MessageRole
    text: str | None
    components: list[dict[str, Any]]
    read: bool
    created_at: datetime
    thread_id: str | None


@dataclass
class MemoryChunkTrace:
    text: str
    score: float
    source: str  # "fact" | "episode" | "profile"


@dataclass
class ToolCallTrace:
    name: str
    result_snippet: str  # first 200 chars of result
    duration_ms: int
    success: bool


@dataclass
class MessageTrace:
    agent: str
    routing_method: str  # "embedding" | "haiku" | "fallback"
    confidence: float
    score_gap: float
    is_compound: bool
    subtasks: list[str]
    memory_chunks: list[MemoryChunkTrace] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    total_duration_ms: int = 0
