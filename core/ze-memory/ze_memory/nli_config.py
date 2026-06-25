from __future__ import annotations

from typing import Any

from ze_memory.defaults import (
    NLI_CONTRADICTION_THRESHOLD,
    NLI_ENTAILMENT_THRESHOLD,
    NLI_GROUNDING_THRESHOLD,
    NLI_LOWER_COSINE_BOUND,
    NLI_RERANK_CANDIDATE_MULTIPLIER,
    NLI_RERANK_MIN_CANDIDATES,
    NLI_RETRIEVAL_RERANK,
    NLI_WRITE_TIME_CHECK,
)


def nli_config(settings: Any = None) -> dict[str, Any]:
    """Resolve NLI thresholds from ZeApiSettings or a raw config dict."""
    memory_cfg: dict = {}
    if settings is not None:
        if hasattr(settings, "config"):
            cfg = settings.config
            if isinstance(cfg, dict):
                memory_cfg = cfg.get("memory", {})
        elif isinstance(settings, dict):
            memory_cfg = settings.get("memory", settings)

    return {
        "nli_contradiction_threshold": memory_cfg.get(
            "nli_contradiction_threshold", NLI_CONTRADICTION_THRESHOLD
        ),
        "nli_entailment_threshold": memory_cfg.get(
            "nli_entailment_threshold", NLI_ENTAILMENT_THRESHOLD
        ),
        "nli_lower_cosine_bound": memory_cfg.get(
            "nli_lower_cosine_bound", NLI_LOWER_COSINE_BOUND
        ),
        "nli_write_time_check": memory_cfg.get(
            "nli_write_time_check", NLI_WRITE_TIME_CHECK
        ),
        "nli_grounding_threshold": memory_cfg.get(
            "nli_grounding_threshold", NLI_GROUNDING_THRESHOLD
        ),
        "nli_retrieval_rerank": memory_cfg.get(
            "nli_retrieval_rerank", NLI_RETRIEVAL_RERANK
        ),
        "nli_rerank_candidate_multiplier": int(
            memory_cfg.get("nli_rerank_candidate_multiplier", NLI_RERANK_CANDIDATE_MULTIPLIER)
        ),
        "nli_rerank_min_candidates": int(
            memory_cfg.get("nli_rerank_min_candidates", NLI_RERANK_MIN_CANDIDATES)
        ),
    }
