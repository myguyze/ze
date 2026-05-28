from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ze_core.capability.types import GateDecision
from ze_core.contacts.types import ContactProposal, PersonContext
from ze_core.memory.types import MemoryContext  # re-exported for AgentContext consumers
from ze_core.progress.reporter import ProgressReporter


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
    contacts: PersonContext = field(default_factory=PersonContext)
    tool_calls: list[ToolCall] = field(default_factory=list)
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
    contact_proposals: list[ContactProposal] = field(default_factory=list)
