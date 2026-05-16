"""Initial application schema — routing_log, user_facts, episodes

Revision ID: 001
Revises: None
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector is needed for episode embeddings (used in Phase 2 memory search).
    # Install via: CREATE EXTENSION IF NOT EXISTS vector;
    # The extension must be available in the Postgres instance.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id    TEXT NOT NULL,
            prompt        TEXT NOT NULL,
            method        TEXT NOT NULL,
            primary_agent TEXT NOT NULL,
            confidence    FLOAT,
            score_gap     FLOAT,
            is_compound   BOOLEAN NOT NULL DEFAULT FALSE,
            raw_scores    JSONB,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS routing_log_session_idx ON routing_log (session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS routing_log_created_idx ON routing_log (created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_facts (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key          TEXT NOT NULL,
            value        TEXT NOT NULL,
            agent        TEXT NOT NULL DEFAULT 'global',
            confidence   FLOAT NOT NULL DEFAULT 1.0,
            reviewed     BOOLEAN NOT NULL DEFAULT FALSE,
            contradicted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS user_facts_agent_key_idx ON user_facts (agent, key)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent      TEXT NOT NULL,
            prompt     TEXT NOT NULL,
            response   TEXT NOT NULL,
            summary    TEXT,
            embedding  VECTOR(384),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # ivfflat index for approximate nearest-neighbour search (Phase 2 memory retrieval).
    # lists=100 is appropriate once the table has ~10k rows; safe to create empty.
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_embedding_idx
        ON episodes USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_agent_created_idx
        ON episodes (agent, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS episodes")
    op.execute("DROP TABLE IF EXISTS user_facts")
    op.execute("DROP TABLE IF EXISTS routing_log")
    # Leave the vector extension in place — it may be shared by other schemas.
