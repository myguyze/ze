"""Re-export ze-core Postgres memory store (Phase 4 migration)."""

from ze_core.memory.postgres import PostgresMemoryStore as MemoryStore
from ze_core.memory.postgres import _cosine_similarity, _parse_update_count

# Helpers kept for tests and any legacy callers.


def _tokens(text: str) -> int:
    return len(text) // 4


def _vec(embedding) -> str:
    from ze_core.memory.postgres import _to_list

    return "[" + ",".join(f"{x:.8f}" for x in _to_list(embedding)) + "]"


__all__ = ["MemoryStore", "_cosine_similarity", "_parse_update_count", "_tokens", "_vec"]
