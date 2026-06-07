from functools import lru_cache

from sentence_transformers import SentenceTransformer


_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def get_embedder(model_name: str = _DEFAULT_MODEL) -> SentenceTransformer:
    """Load and cache the sentence-transformer model.

    Called once during FastAPI lifespan. The lru_cache ensures a single
    instance is shared across routing and memory modules.
    """
    return SentenceTransformer(model_name)
