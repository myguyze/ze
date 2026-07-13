from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from scipy.special import softmax

if TYPE_CHECKING:
    from sentence_transformers.cross_encoder import CrossEncoder

_NLI_MODEL_ID = "cross-encoder/nli-deberta-v3-small"
_model: CrossEncoder | None = None


def get_nli_model() -> CrossEncoder:
    global _model
    if _model is None:
        from sentence_transformers.cross_encoder import CrossEncoder

        _model = CrossEncoder(_NLI_MODEL_ID)
    return _model


def is_latin(text: str) -> bool:
    """Heuristic: at least 80% of word chars are ASCII."""
    chars = [c for c in text if c.isalpha()]
    return not chars or sum(1 for c in chars if ord(c) < 128) / len(chars) >= 0.8


def pair_is_scorable(premise: str, hypothesis: str) -> bool:
    return is_latin(premise) and is_latin(hypothesis)


def filter_scorable_pairs(
    pairs: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[int]]:
    """Return scorable pairs and their original indices."""
    scorable: list[tuple[str, str]] = []
    indices: list[int] = []
    for idx, (premise, hypothesis) in enumerate(pairs):
        if pair_is_scorable(premise, hypothesis):
            scorable.append((premise, hypothesis))
            indices.append(idx)
    return scorable, indices


def nli_scores(pairs: list[tuple[str, str]]) -> list[dict[str, float] | None]:
    """Return NLI probabilities per pair; None when the pair is skipped (non-Latin)."""
    if not pairs:
        return []

    scorable, scorable_indices = filter_scorable_pairs(pairs)
    scored_by_index: dict[int, dict[str, float]] = {}

    if scorable:
        model = get_nli_model()
        raw = model.predict(scorable)
        probs = softmax(raw, axis=1)
        for idx, prob in zip(scorable_indices, probs):
            scored_by_index[idx] = {
                "contradiction": float(prob[0]),
                "neutral": float(prob[1]),
                "entailment": float(prob[2]),
            }

    return [scored_by_index.get(i) for i in range(len(pairs))]


async def nli_scores_async(
    pairs: list[tuple[str, str]],
) -> list[dict[str, float] | None]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, nli_scores, pairs)


def nli_grounding_score(
    hypothesis: str,
    evidence_texts: list[str],
    scores: list[dict[str, float] | None] | None = None,
) -> float:
    """Mean entailment probability across evidence texts supporting a hypothesis."""
    if not evidence_texts:
        return 0.0

    pairs = [(text, hypothesis) for text in evidence_texts]
    resolved = scores if scores is not None else nli_scores(pairs)
    entailments = [s["entailment"] for s in resolved if s is not None]
    if not entailments:
        return 0.0
    return float(sum(entailments) / len(entailments))


class LocalNLIClient:
    """CPU cross-encoder NLI — satisfies NLIClient."""

    async def scores(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[dict[str, float] | None]:
        return await nli_scores_async(pairs)

    def grounding_score(
        self,
        hypothesis: str,
        evidence_texts: list[str],
        scores: list[dict[str, float] | None] | None = None,
    ) -> float:
        return nli_grounding_score(hypothesis, evidence_texts, scores=scores)

    def pair_is_scorable(self, premise: str, hypothesis: str) -> bool:
        return pair_is_scorable(premise, hypothesis)
