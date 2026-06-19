"""memory_session_summaries table for eager session narrative summaries (Phase 65)."""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_session_summaries (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id         TEXT        NOT NULL UNIQUE,
            summary            TEXT        NOT NULL,
            episode_count      INT         NOT NULL,
            last_turn_at       TIMESTAMPTZ NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            summary_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            embedding          VECTOR(384)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_session_summaries_updated_idx"
        " ON memory_session_summaries (summary_updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_session_summaries_embedding_idx"
        " ON memory_session_summaries"
        " USING ivfflat (embedding vector_cosine_ops)"
        " WITH (lists = 10)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_session_summaries")
