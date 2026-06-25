from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

FlagType = Literal[
    "betteridge",
    "clickbait",
    "vague_attribution",
    "headline_mismatch",
    "weasel_words",
    "emotional_manipulation",
    "passive_agency",
    "false_balance",
    "missing_context",
    "sensationalism",
]

FlagConfidence = Literal["high", "low"]

# High-confidence: shown inline in briefing, counted in summary.
# Low-confidence: available in get_headlines and agent responses only.
FLAG_CONFIDENCE: dict[str, FlagConfidence] = {
    "betteridge": "high",
    "clickbait": "high",
    "vague_attribution": "high",
    "headline_mismatch": "high",
    "weasel_words": "low",
    "emotional_manipulation": "low",
    "passive_agency": "low",
    "false_balance": "low",
    "missing_context": "low",
    "sensationalism": "low",
}

AnalysisStatus = Literal["pending", "heuristic_only", "complete", "failed"]


@dataclass
class CredibilityFlag:
    type: str
    label: str
    detail: str
    source: Literal["heuristic", "llm", "nli"]
    confidence: FlagConfidence
    lang: str = "any"


@dataclass
class CredibilityReport:
    flags: list[CredibilityFlag] = field(default_factory=list)
    status: AnalysisStatus = "pending"
    analyzed_at: datetime | None = None
    model: str | None = None
    prompt_version: str | None = None

    @property
    def high_confidence_flags(self) -> list[CredibilityFlag]:
        return [f for f in self.flags if f.confidence == "high"]

    @property
    def is_briefing_worthy(self) -> bool:
        hf = self.high_confidence_flags
        return len(hf) >= 2 or any(
            f.type in ("betteridge", "clickbait", "headline_mismatch") for f in hf
        )


@dataclass
class Article:
    url: str
    source_key: str
    title: str
    summary: str
    published_at: datetime
    tags: list[str] = field(default_factory=list)
    credibility: CredibilityReport | None = None


@dataclass
class SourceConfig:
    key: str
    type: str
    url: str
    tags: list[str] = field(default_factory=list)


@dataclass
class NewsPreference:
    topic: str
    polarity: Literal["include", "exclude"]
    source: Literal["fact", "profile", "goal", "query"]
    weight: float
    reason: str
    confidence: float = 1.0


@dataclass
class PersonalizationSettings:
    enabled: bool = True
    explore_ratio: float = 0.2
    min_preferences: int = 2
    max_per_topic: int = 2
    candidate_multiplier: int = 4
    fact_days: int = 365
    fact_limit: int = 100
    min_confidence: float = 0.65

    @classmethod
    def from_config(cls, news_cfg: dict) -> PersonalizationSettings:
        cfg = news_cfg.get("personalization", {})
        min_preferences = cfg.get("min_preferences")
        if min_preferences is None:
            min_preferences = cfg.get("min_facts", 2)
        return cls(
            enabled=bool(cfg.get("enabled", True)),
            explore_ratio=float(cfg.get("explore_ratio", 0.2)),
            min_preferences=int(min_preferences),
            max_per_topic=int(cfg.get("max_per_topic", 2)),
            candidate_multiplier=int(cfg.get("candidate_multiplier", 4)),
            fact_days=int(cfg.get("fact_days", 365)),
            fact_limit=int(cfg.get("fact_limit", 100)),
            min_confidence=float(cfg.get("min_confidence", 0.65)),
        )


@dataclass
class PersonalizationContext:
    interest_text: str = ""
    exclusions: list[str] = field(default_factory=list)
    explore_ratio: float = 0.2
    fact_count: int = 0
    query_text: str = ""
    preferences: list[NewsPreference] = field(default_factory=list)
    max_per_topic: int = 2
    candidate_multiplier: int = 4


@runtime_checkable
class GoalTitleProvider(Protocol):
    async def list_active_goal_titles(self) -> list[str]: ...
