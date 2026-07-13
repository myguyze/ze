"""Three pre-gates that every staged dream artifact must pass before the LLM critic."""

from __future__ import annotations

import re
from typing import Any

from ze_logging import get_logger
from ze_memory.consolidation_store import _cosine_similarity

log = get_logger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_DEFAULT_NLI_THRESHOLD = 0.75
_DEFAULT_NOVELTY_THRESHOLD = 0.92


def _split_atomic(text: str) -> list[str]:
    sentences = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


class ScoringGates:
    """Stateless gate evaluator — results are stored back on the artifact by the caller."""

    def __init__(
        self,
        pool: Any,
        embedder: Any,
        nli_client: Any | None = None,
        llm_client: Any | None = None,
        nli_threshold: float = _DEFAULT_NLI_THRESHOLD,
        novelty_threshold: float = _DEFAULT_NOVELTY_THRESHOLD,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._nli = nli_client
        self._llm = llm_client
        self._nli_threshold = nli_threshold
        self._novelty_threshold = novelty_threshold

    # ------------------------------------------------------------------
    # Gate 1 — NLI groundedness
    # ------------------------------------------------------------------

    async def gate1_nli(
        self,
        content: str,
        source_texts: list[str],
        synthesis_model: str = "anthropic/claude-haiku-4-5",
    ) -> tuple[bool, float]:
        """Return (pass, faithfulness_score)."""
        if not source_texts:
            return False, 0.0

        sentences = _split_atomic(content)
        if not sentences:
            return False, 0.0

        # Non-English fallback: use LLM groundedness check
        if self._nli is None or not _all_latin(content):
            return await self._gate1_llm_fallback(
                sentences, source_texts, synthesis_model
            )

        pairs = [(src, sent) for sent in sentences for src in source_texts]
        try:
            scores = await self._nli.scores(pairs)
        except Exception as exc:
            log.warning("gate1_nli_error", error=str(exc))
            return await self._gate1_llm_fallback(
                sentences, source_texts, synthesis_model
            )

        n_sources = len(source_texts)
        supported = 0
        for i, sent in enumerate(sentences):
            sent_scores = scores[i * n_sources : (i + 1) * n_sources]
            if any(
                s is not None and s.get("entailment", 0.0) >= 0.50 for s in sent_scores
            ):
                supported += 1

        faithfulness = supported / len(sentences)
        passed = faithfulness >= self._nli_threshold
        return passed, faithfulness

    async def _gate1_llm_fallback(
        self,
        sentences: list[str],
        source_texts: list[str],
        model: str,
    ) -> tuple[bool, float]:
        if self._llm is None:
            return False, 0.0
        source_block = "\n---\n".join(source_texts[:5])
        prompt = (
            "Rate what fraction of the following CLAIM sentences are fully supported by the SOURCE.\n"
            "Answer with a single decimal between 0.0 and 1.0 only.\n\n"
            f"SOURCE:\n{source_block}\n\n"
            f"CLAIM:\n{chr(10).join(sentences)}"
        )
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.0,
                max_tokens=10,
            )
            score = float(raw.strip().split()[0])
            score = max(0.0, min(1.0, score))
            return score >= self._nli_threshold, score
        except Exception as exc:
            log.warning("gate1_llm_fallback_error", error=str(exc))
            return False, 0.0

    # ------------------------------------------------------------------
    # Gate 2 — Embedding novelty
    # ------------------------------------------------------------------

    async def gate2_novelty(
        self,
        content: str,
        threshold: float | None = None,
    ) -> tuple[bool, float]:
        """Return (pass, novelty_score) where novelty = 1 - max_cosine_sim."""
        if self._embedder is None:
            return True, 1.0

        threshold = threshold if threshold is not None else self._novelty_threshold
        content_emb = self._embedder.encode(content)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT embedding FROM memory_facts
                WHERE contradicted = false
                  AND provenance != 'synthesized'
                  AND embedding IS NOT NULL
                LIMIT 500
                """
            )

        if not rows:
            return True, 1.0

        max_sim = max(
            _cosine_similarity(content_emb, row["embedding"])
            for row in rows
            if row["embedding"] is not None
        )
        novelty = 1.0 - max_sim
        passed = max_sim < threshold
        return passed, novelty

    # ------------------------------------------------------------------
    # Gate 3 — Embedding retrievability
    # ------------------------------------------------------------------

    async def gate3_retrievability(
        self,
        content: str,
        source_episode_ids: list[Any],
        support_count: int = 1,
    ) -> bool:
        """Require at least 1 source episode in the top-3 retrieved (top-5 if support >= 5)."""
        if self._embedder is None or not source_episode_ids:
            return True

        content_emb = self._embedder.encode(content)
        top_k = 5 if support_count >= 5 else 3

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, embedding FROM memory_episodes
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                list(content_emb),
                top_k,
            )

        if not rows:
            return False

        retrieved_ids = {str(r["id"]) for r in rows}
        source_ids = {str(eid) for eid in source_episode_ids}
        return bool(retrieved_ids & source_ids)


def _all_latin(text: str) -> bool:
    chars = [c for c in text if c.isalpha()]
    return not chars or sum(1 for c in chars if ord(c) < 128) / len(chars) >= 0.8
