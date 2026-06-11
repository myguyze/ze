from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ze_core.defaults import (
    MODEL_ROUTER_FALLBACK,
    ROUTING_GAP_THRESHOLD,
    ROUTING_THRESHOLD,
)


@dataclass
class SubTask:
    agent: str
    intent: str
    prompt: str
    model: str = ""


@dataclass
class RoutingEnvelope:
    primary_agent: str
    confidence: float
    score_gap: float
    routing_method: str        # "embedding" | "haiku" | "fallback"
    is_compound: bool
    subtasks: list[SubTask]
    requires_synthesis: bool
    raw_scores: dict[str, float] = field(default_factory=dict)
    is_sequential: bool = False
    complexity: str = "complex"  # "simple" | "complex"


@dataclass
class RouterConfig:
    threshold: float = ROUTING_THRESHOLD
    gap_threshold: float = ROUTING_GAP_THRESHOLD
    fallback_model: str = MODEL_ROUTER_FALLBACK


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        **kwargs: Any,
    ) -> str: ...

    async def complete_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> tuple[str | None, list[dict] | None]: ...
