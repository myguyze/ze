from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ze_logging import get_logger
from ze_memory.defaults import (
    COMPOSITE_WEIGHT_CONFIDENCE_DEFAULT,
    COMPOSITE_WEIGHT_RECENCY_DEFAULT,
    COMPOSITE_WEIGHT_SIMILARITY_DEFAULT,
    ENTITY_ANCHOR_ENABLED_DEFAULT,
    ENTITY_MATCH_CONSTANT_DEFAULT,
    LIVE_RERANK_CANDIDATE_LIMIT_DEFAULT,
    LIVE_RERANK_ENABLED_DEFAULT,
    LIVE_RERANK_TIMEOUT_MS_DEFAULT,
    RELEVANCE_FLOOR_DEFAULT,
)

log = get_logger(__name__)


@dataclass
class CompositeWeights:
    similarity: float = COMPOSITE_WEIGHT_SIMILARITY_DEFAULT
    recency: float = COMPOSITE_WEIGHT_RECENCY_DEFAULT
    confidence: float = COMPOSITE_WEIGHT_CONFIDENCE_DEFAULT


@dataclass
class RelevanceConfig:
    floor: float = RELEVANCE_FLOOR_DEFAULT
    floor_overrides: dict[str, float] = field(default_factory=dict)
    composite_weights: CompositeWeights = field(default_factory=CompositeWeights)
    entity_anchor_enabled: bool = ENTITY_ANCHOR_ENABLED_DEFAULT
    entity_match_constant: float = ENTITY_MATCH_CONSTANT_DEFAULT
    live_rerank_enabled: bool = LIVE_RERANK_ENABLED_DEFAULT
    live_rerank_candidate_limit: int = LIVE_RERANK_CANDIDATE_LIMIT_DEFAULT
    live_rerank_timeout_ms: int = LIVE_RERANK_TIMEOUT_MS_DEFAULT


def _resolve_memory_cfg(settings: Any) -> dict:
    if settings is None:
        return {}
    if hasattr(settings, "config"):
        cfg = settings.config
        if isinstance(cfg, dict):
            return cfg.get("memory", {}) or {}
        return {}
    if isinstance(settings, dict):
        return settings.get("memory", settings) or {}
    return {}


def relevance_config(settings: Any = None) -> RelevanceConfig:
    """Resolve relevance/composite/entity-anchor/live-rerank config.

    Mirrors nli_config()'s tolerance pattern — a malformed `memory:` section
    never raises, it falls back to defaults.py constants with a log.warning.
    """
    try:
        memory_cfg = _resolve_memory_cfg(settings)

        floor_overrides_raw = memory_cfg.get("relevance_floor_overrides", {}) or {}
        floor_overrides = {
            str(k): float(v) for k, v in dict(floor_overrides_raw).items()
        }

        weights_raw = memory_cfg.get("composite_weights", {}) or {}
        weights = CompositeWeights(
            similarity=float(
                weights_raw.get("similarity", COMPOSITE_WEIGHT_SIMILARITY_DEFAULT)
            ),
            recency=float(
                weights_raw.get("recency", COMPOSITE_WEIGHT_RECENCY_DEFAULT)
            ),
            confidence=float(
                weights_raw.get("confidence", COMPOSITE_WEIGHT_CONFIDENCE_DEFAULT)
            ),
        )

        entity_anchor_raw = memory_cfg.get("entity_anchor", {}) or {}
        live_rerank_raw = memory_cfg.get("live_rerank", {}) or {}

        return RelevanceConfig(
            floor=float(memory_cfg.get("relevance_floor", RELEVANCE_FLOOR_DEFAULT)),
            floor_overrides=floor_overrides,
            composite_weights=weights,
            entity_anchor_enabled=bool(
                entity_anchor_raw.get("enabled", ENTITY_ANCHOR_ENABLED_DEFAULT)
            ),
            entity_match_constant=float(
                entity_anchor_raw.get(
                    "match_constant", ENTITY_MATCH_CONSTANT_DEFAULT
                )
            ),
            live_rerank_enabled=bool(
                live_rerank_raw.get("enabled", LIVE_RERANK_ENABLED_DEFAULT)
            ),
            live_rerank_candidate_limit=int(
                live_rerank_raw.get(
                    "candidate_limit", LIVE_RERANK_CANDIDATE_LIMIT_DEFAULT
                )
            ),
            live_rerank_timeout_ms=int(
                live_rerank_raw.get("timeout_ms", LIVE_RERANK_TIMEOUT_MS_DEFAULT)
            ),
        )
    except Exception as exc:
        log.warning("relevance_config_malformed_fallback", error=str(exc))
        return RelevanceConfig()
