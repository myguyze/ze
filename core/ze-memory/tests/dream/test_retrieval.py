"""Tests for dream/retrieval.py — episode retrievability SQL helper."""
from __future__ import annotations

from ze_memory.dream.retrieval import episode_retrievable_sql


def test_episode_retrievable_sql_excludes_archived_and_decayed():
    sql = episode_retrievable_sql()
    assert "memory_episode_metadata" in sql
    assert "provenance = 'archived'" in sql
    assert "retrieval_weight" in sql


def test_episode_retrievable_sql_uses_episode_table_alias():
    sql = episode_retrievable_sql("ep")
    assert "em.episode_id = ep.id" in sql
