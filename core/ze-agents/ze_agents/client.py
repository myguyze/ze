"""LLMClient protocol — the interface BaseAgent calls during agentic_loop.

The concrete OpenRouterClient in ze-core satisfies this protocol structurally.
Ze-agents depends only on this protocol, not on any concrete implementation.
"""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        *,
        response_format: dict | None = None,
        reasoning: dict | None = None,
        audio_seconds: float | None = None,
    ) -> str: ...

    async def complete_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        system: str | None = None,
        max_tokens: int = 2000,
    ) -> tuple[str | None, list[dict[str, Any]] | None]: ...

    async def stream_complete_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        system: str | None = None,
        max_tokens: int = 2000,
        token_sink: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None]: ...
