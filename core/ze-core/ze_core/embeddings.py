from __future__ import annotations

from functools import lru_cache
from typing import Union

import numpy as np
from sentence_transformers import SentenceTransformer


_DEFAULT_MODEL = "intfloat/multilingual-e5-base"


class E5Embedder:
    """SentenceTransformer wrapper that enforces E5's query/passage prefix contract.

    E5 models require asymmetric prefixes to produce discriminative similarity
    scores. Without them, scores cluster in a narrow 0.3–0.5 band regardless of
    match quality — identical to the paraphrase-model problem we're replacing.

    - encode_query: user messages and search queries
    - encode_passage: agent descriptions and stored content
    - encode: compat shim for memory layer; treats all inputs as passages
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model = SentenceTransformer(model_name)

    def encode_query(
        self,
        text: str,
        normalize_embeddings: bool = True,
        **kwargs,
    ) -> np.ndarray:
        return self._model.encode(
            f"query: {text}",
            normalize_embeddings=normalize_embeddings,
            **kwargs,
        )

    def encode_passage(
        self,
        text: Union[str, list[str]],
        normalize_embeddings: bool = True,
        **kwargs,
    ) -> np.ndarray:
        if isinstance(text, list):
            prefixed = [f"passage: {t}" for t in text]
        else:
            prefixed = f"passage: {text}"
        return self._model.encode(
            prefixed,
            normalize_embeddings=normalize_embeddings,
            **kwargs,
        )

    def encode(
        self,
        text: Union[str, list[str]],
        normalize_embeddings: bool = True,
        **kwargs,
    ) -> np.ndarray:
        """Compat shim for memory layer callers — treats all inputs as passages."""
        return self.encode_passage(
            text, normalize_embeddings=normalize_embeddings, **kwargs
        )


@lru_cache(maxsize=1)
def get_embedder(model_name: str = _DEFAULT_MODEL) -> E5Embedder:
    """Load and cache the E5 embedder.

    Called once during FastAPI lifespan. The lru_cache ensures a single
    instance is shared across routing and memory modules.
    """
    return E5Embedder(model_name)
