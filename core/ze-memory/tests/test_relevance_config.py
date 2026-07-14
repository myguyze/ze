"""Tests for ze_memory.relevance_config.relevance_config()."""

from __future__ import annotations

from ze_memory.defaults import (
    ENTITY_MATCH_CONSTANT_DEFAULT,
    RELEVANCE_FLOOR_DEFAULT,
)
from ze_memory.relevance_config import CompositeWeights, RelevanceConfig, relevance_config


def test_relevance_config_defaults_with_no_settings():
    cfg = relevance_config(None)
    assert isinstance(cfg, RelevanceConfig)
    assert cfg.floor == RELEVANCE_FLOOR_DEFAULT
    assert cfg.floor_overrides == {}
    assert isinstance(cfg.composite_weights, CompositeWeights)
    assert cfg.entity_anchor_enabled is True
    assert cfg.entity_match_constant == ENTITY_MATCH_CONSTANT_DEFAULT
    assert cfg.live_rerank_enabled is True


def test_relevance_config_reads_yaml_overrides_from_dict_settings():
    settings = {
        "memory": {
            "relevance_floor": 0.5,
            "relevance_floor_overrides": {"episode": 0.2},
            "composite_weights": {
                "similarity": 0.7,
                "recency": 0.2,
                "confidence": 0.1,
            },
            "entity_anchor": {"enabled": False, "match_constant": 0.9},
            "live_rerank": {
                "enabled": False,
                "candidate_limit": 5,
                "timeout_ms": 50,
            },
        }
    }
    cfg = relevance_config(settings)
    assert cfg.floor == 0.5
    assert cfg.floor_overrides == {"episode": 0.2}
    assert cfg.composite_weights.similarity == 0.7
    assert cfg.composite_weights.recency == 0.2
    assert cfg.composite_weights.confidence == 0.1
    assert cfg.entity_anchor_enabled is False
    assert cfg.entity_match_constant == 0.9
    assert cfg.live_rerank_enabled is False
    assert cfg.live_rerank_candidate_limit == 5
    assert cfg.live_rerank_timeout_ms == 50


def test_relevance_config_reads_from_settings_config_attr():
    class FakeSettings:
        config = {"memory": {"relevance_floor": 0.1}}

    cfg = relevance_config(FakeSettings())
    assert cfg.floor == 0.1


def test_relevance_config_tolerates_malformed_config():
    settings = {"memory": {"composite_weights": "not-a-dict"}}
    cfg = relevance_config(settings)
    assert cfg.floor == RELEVANCE_FLOOR_DEFAULT
    assert isinstance(cfg.composite_weights, CompositeWeights)


def test_relevance_config_never_raises_on_garbage_settings():
    cfg = relevance_config(object())
    assert isinstance(cfg, RelevanceConfig)
    assert cfg.floor == RELEVANCE_FLOOR_DEFAULT
