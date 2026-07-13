"""Tests for ze_core/nli.py — NLI cross-encoder helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from ze_core.nli import (
    LocalNLIClient,
    filter_scorable_pairs,
    is_latin,
    nli_grounding_score,
    nli_scores,
    nli_scores_async,
    pair_is_scorable,
)


def test_is_latin_english():
    assert is_latin("User eats healthy food")


def test_is_latin_non_latin_script():
    assert not is_latin("用户喜欢吃蔬菜")


def test_pair_is_scorable_requires_both_latin():
    assert pair_is_scorable("hello", "world")
    assert not pair_is_scorable("hello", "用户")


def test_filter_scorable_pairs_preserves_indices():
    pairs = [("a", "b"), ("x", "用户"), ("c", "d")]
    scorable, indices = filter_scorable_pairs(pairs)
    assert scorable == [("a", "b"), ("c", "d")]
    assert indices == [0, 2]


@patch("ze_core.nli.get_nli_model")
def test_nli_scores_returns_shape(mock_get_model):
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array(
        [
            [2.0, 0.5, -1.0],
            [-1.0, 0.0, 2.0],
        ]
    )
    mock_get_model.return_value = mock_model

    result = nli_scores([("premise one", "hypothesis one"), ("p2", "h2")])

    assert len(result) == 2
    assert result[0] is not None
    assert set(result[0]) == {"contradiction", "neutral", "entailment"}
    assert abs(sum(result[0].values()) - 1.0) < 1e-5


@patch("ze_core.nli.get_nli_model")
def test_nli_scores_skips_non_latin_pairs(mock_get_model):
    mock_model = MagicMock()
    mock_get_model.return_value = mock_model

    result = nli_scores([("hello", "用户")])

    assert result == [None]
    mock_model.predict.assert_not_called()


@patch("ze_core.nli.nli_scores")
async def test_nli_scores_async_delegates(mock_scores):
    mock_scores.return_value = [
        {"contradiction": 0.1, "neutral": 0.2, "entailment": 0.7}
    ]
    result = await nli_scores_async([("a", "b")])
    assert result[0]["entailment"] == 0.7


def test_nli_grounding_score_mean_entailment():
    scores = [
        {"contradiction": 0.1, "neutral": 0.2, "entailment": 0.7},
        {"contradiction": 0.2, "neutral": 0.1, "entailment": 0.7},
    ]
    assert nli_grounding_score("hypothesis", ["e1", "e2"], scores=scores) == 0.7


async def test_local_nli_client_scores():
    client = LocalNLIClient()
    with patch("ze_core.nli.nli_scores_async", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = [
            {"contradiction": 0.1, "neutral": 0.2, "entailment": 0.7}
        ]
        result = await client.scores([("a", "b")])
        assert result[0]["entailment"] == 0.7


def test_local_nli_client_grounding_score():
    client = LocalNLIClient()
    scores = [{"contradiction": 0.1, "neutral": 0.2, "entailment": 0.8}]
    assert client.grounding_score("hyp", ["ev"], scores=scores) == 0.8


@pytest.mark.slow
def test_nli_model_loads_real_weights():
    from ze_core.nli import get_nli_model

    model = get_nli_model()
    assert model is not None
