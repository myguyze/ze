from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedder(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """Load and cache the sentence-transformer model.

    Called once during FastAPI lifespan. The lru_cache ensures a single
    instance is shared across routing and memory modules.
    """
    return SentenceTransformer(model_name)
