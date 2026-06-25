from __future__ import annotations

from ze_memory.defaults import FORGETTING_WEIGHT_THRESHOLD


def episode_retrievable_sql(episode_table: str = "memory_episodes") -> str:
    """SQL AND clause excluding decayed or archived episodes from retrieval."""
    threshold = FORGETTING_WEIGHT_THRESHOLD
    return f"""
      AND NOT EXISTS (
        SELECT 1 FROM memory_episode_metadata em
        WHERE em.episode_id = {episode_table}.id
          AND (
            em.provenance = 'archived'
            OR em.retrieval_weight <= {threshold}
          )
      )
    """
