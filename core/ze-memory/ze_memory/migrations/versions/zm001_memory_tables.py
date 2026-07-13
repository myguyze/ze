"""Memory package tables.

Revision ID: zm001
Revises:
Branch labels: ze_memory
Depends on: zc001
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_memory",)
depends_on: Union[str, Sequence[str], None] = "zc001"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_entities (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type    TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            aliases        JSONB NOT NULL DEFAULT '[]'::jsonb,
            attrs          JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding      VECTOR(384),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_entities_embedding_idx
            ON memory_entities USING hnsw (embedding vector_cosine_ops)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_facts (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id         UUID NULL REFERENCES memory_entities(id),
            predicate          TEXT NOT NULL,
            object_text        TEXT NULL,
            object_id          UUID NULL REFERENCES memory_entities(id),
            value              TEXT NOT NULL,
            confidence         FLOAT NOT NULL DEFAULT 1.0,
            reviewed           BOOLEAN NOT NULL DEFAULT false,
            contradicted       BOOLEAN NOT NULL DEFAULT false,
            source_episode_id  UUID NULL,
            source_refs        JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding          VECTOR(384),
            expires_at         TIMESTAMPTZ NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_facts_embedding_idx
            ON memory_facts USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_facts_active_idx
            ON memory_facts (predicate, updated_at DESC)
            WHERE contradicted = false
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_episodes (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id        TEXT NOT NULL,
            agent             TEXT NOT NULL,
            prompt            TEXT NOT NULL,
            response          TEXT NOT NULL,
            summary           TEXT NULL,
            relevance         FLOAT NOT NULL DEFAULT 0.0,
            linked_entity_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            linked_fact_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding         VECTOR(384),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_episodes_embedding_idx
            ON memory_episodes USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_episodes_created_at_idx
            ON memory_episodes (created_at DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_events (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type        TEXT NOT NULL,
            title             TEXT NOT NULL,
            start_at          TIMESTAMPTZ NULL,
            end_at            TIMESTAMPTZ NULL,
            participants      JSONB NOT NULL DEFAULT '[]'::jsonb,
            roles             JSONB NOT NULL DEFAULT '{}'::jsonb,
            summary           TEXT NULL,
            outcome           TEXT NULL,
            source_episode_id UUID NULL,
            embedding         VECTOR(384),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_procedures (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name             TEXT NOT NULL,
            trigger          TEXT NOT NULL,
            preconditions    JSONB NOT NULL DEFAULT '[]'::jsonb,
            steps            JSONB NOT NULL DEFAULT '[]'::jsonb,
            success_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
            version          INT NOT NULL DEFAULT 1,
            source_refs      JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding        VECTOR(384),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_procedures_embedding_idx
            ON memory_procedures USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_task_state (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id      UUID NULL,
            goal_id      UUID NULL,
            status       TEXT NOT NULL,
            open_steps   JSONB NOT NULL DEFAULT '[]'::jsonb,
            blocked_by   JSONB NOT NULL DEFAULT '[]'::jsonb,
            last_action  TEXT NULL,
            next_action  TEXT NULL,
            tool_cursors JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT memory_task_state_task_id_uniq UNIQUE (task_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_profile_facets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key         TEXT NOT NULL UNIQUE,
            value       TEXT NOT NULL,
            stability   TEXT NOT NULL DEFAULT 'dynamic',
            confidence  FLOAT NOT NULL DEFAULT 1.0,
            source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_profile_facets")
    op.execute("DROP TABLE IF EXISTS memory_task_state")
    op.execute("DROP TABLE IF EXISTS memory_procedures")
    op.execute("DROP TABLE IF EXISTS memory_events")
    op.execute("DROP TABLE IF EXISTS memory_episodes")
    op.execute("DROP TABLE IF EXISTS memory_facts")
    op.execute("DROP TABLE IF EXISTS memory_entities")
