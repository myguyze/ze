"""correlation_hypothesis table for the correlation engine (Phase 57)."""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS correlation_hypothesis (
            id           UUID PRIMARY KEY,
            summary      TEXT NOT NULL,
            narrative    TEXT NOT NULL,
            relation     TEXT NOT NULL,
            confidence   REAL NOT NULL,
            relevance    REAL NOT NULL,
            evidence     JSONB NOT NULL,
            entities     JSONB NOT NULL,
            surfaced     BOOLEAN NOT NULL DEFAULT false,
            feedback     TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS correlation_hypothesis_created_idx"
        " ON correlation_hypothesis (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS correlation_hypothesis_surfaced_idx"
        " ON correlation_hypothesis (surfaced) WHERE surfaced = false"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS correlation_hypothesis")
