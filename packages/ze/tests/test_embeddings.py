import pytest
import numpy as np
from ze_core.embeddings import get_embedder


@pytest.fixture(autouse=True)
def clear_embedder_cache():
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


@pytest.mark.slow
def test_embedder_returns_sentence_transformer():
    from sentence_transformers import SentenceTransformer
    embedder = get_embedder()
    assert isinstance(embedder, SentenceTransformer)


@pytest.mark.slow
def test_embedder_is_singleton():
    e1 = get_embedder()
    e2 = get_embedder()
    assert e1 is e2


@pytest.mark.slow
def test_embedder_produces_384_dim_vector():
    embedder = get_embedder()
    vec = embedder.encode("hello world")
    assert vec.shape == (384,)


@pytest.mark.slow
def test_embedder_vectors_are_normalised():
    embedder = get_embedder()
    vec = embedder.encode("test sentence")
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-5


@pytest.mark.slow
def test_embedder_batch_encode():
    embedder = get_embedder()
    vecs = embedder.encode(["hello", "world", "test"])
    assert vecs.shape == (3, 384)


@pytest.mark.slow
def test_different_sentences_produce_different_vectors():
    embedder = get_embedder()
    v1 = embedder.encode("book a calendar event for tomorrow")
    v2 = embedder.encode("search the web for latest news")
    similarity = float(np.dot(v1, v2))
    assert similarity < 0.99  # not identical
