from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import numpy as np


@dataclass
class UserFact:
    key: str
    value: str
    agent: str = "global"
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    id: UUID | None = None          # None before first DB persist
    updated_at: datetime | None = None


@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    summary: str | None = None
    relevance: float = 0.0          # populated at retrieval time, never persisted
    id: UUID | None = None
    created_at: datetime | None = None
    # embedding is write-time only; left None in context objects so that
    # AgentState remains JSON-serialisable for the LangGraph checkpointer.
    embedding: np.ndarray | None = field(default=None, repr=False, compare=False)


@dataclass
class MemoryContext:
    facts: list[UserFact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    token_estimate: int = 0
