from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserFact:
    content: str
    confidence: float = 1.0
    agent: str = ""


@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    relevance: float = 1.0


@dataclass
class MemoryContext:
    facts: list[UserFact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
