"""NLIClient protocol — local cross-encoder inference for entailment/contradiction."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NLIClient(Protocol):
    async def scores(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[dict[str, float] | None]: ...

    def grounding_score(
        self,
        hypothesis: str,
        evidence_texts: list[str],
        scores: list[dict[str, float] | None] | None = None,
    ) -> float: ...

    def pair_is_scorable(self, premise: str, hypothesis: str) -> bool: ...
