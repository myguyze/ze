from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


# Phase 1 stubs — flesh out fully in Phase 2 (spec: 03-memory.md)

@dataclass
class UserFact:
    key: str
    value: str
    agent: str = "global"
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    id: UUID | None = None
    updated_at: datetime | None = None


@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    summary: str | None = None
    relevance: float = 0.0
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class MemoryContext:
    facts: list[UserFact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    token_estimate: int = 0
