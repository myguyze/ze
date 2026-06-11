"""Initial schema: user_facts, episodes, user_profile, routing_log

Revision ID: zc001
Revises:
Create Date: 2025-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_core",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_facts (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            key          TEXT        NOT NULL,
            value        TEXT        NOT NULL,
            agent        TEXT        NOT NULL DEFAULT 'global',
            confidence   FLOAT       NOT NULL DEFAULT 1.0,
            reviewed     BOOLEAN     NOT NULL DEFAULT false,
            contradicted BOOLEAN     NOT NULL DEFAULT false,
            embedding    VECTOR(384),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS user_facts_retrieval_idx
            ON user_facts (contradicted, agent, updated_at DESC)
        """
    )
    # HNSW index for semantic fact ordering in get_context().
    # HNSW can be built on an empty table, unlike IVFFlat.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS user_facts_embedding_idx
            ON user_facts USING hnsw (embedding vector_cosine_ops)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            agent      TEXT        NOT NULL,
            prompt     TEXT        NOT NULL,
            response   TEXT        NOT NULL,
            summary    TEXT,
            embedding  VECTOR(384),
            is_archive BOOLEAN     NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS episodes_created_idx
            ON episodes (created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS episodes_embedding_idx
            ON episodes USING hnsw (embedding vector_cosine_ops)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profile (
            id            INT         PRIMARY KEY DEFAULT 1,
            preferences   TEXT        NOT NULL DEFAULT '',
            habits        TEXT        NOT NULL DEFAULT '',
            topics        TEXT        NOT NULL DEFAULT '',
            relationships TEXT        NOT NULL DEFAULT '',
            goals         TEXT        NOT NULL DEFAULT '',
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            version       INT         NOT NULL DEFAULT 0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS routing_log (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id     TEXT        NOT NULL,
            prompt         TEXT        NOT NULL,
            method         TEXT        NOT NULL,
            primary_agent  TEXT        NOT NULL,
            confidence     FLOAT       NOT NULL,
            score_gap      FLOAT       NOT NULL,
            is_compound    BOOLEAN     NOT NULL,
            raw_scores     JSONB       NOT NULL DEFAULT '{}',
            complexity     TEXT,
            model_selected TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS routing_log_session_idx
            ON routing_log (session_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS routing_log")
    op.execute("DROP TABLE IF EXISTS user_profile")
    op.execute("DROP TABLE IF EXISTS episodes")
    op.execute("DROP TABLE IF EXISTS user_facts")
    # Intentionally not dropping the vector extension — other schemas may use it.
