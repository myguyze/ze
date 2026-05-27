from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostRecord:
    agent: str
    flow_type: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    session_id: str | None
    cost_usd: float | None
    generation_id: str | None
    audio_seconds: float | None = None


@dataclass
class UsageInfo:
    """Usage metadata returned alongside a completion response."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    generation_id: str | None
    duration_ms: int
