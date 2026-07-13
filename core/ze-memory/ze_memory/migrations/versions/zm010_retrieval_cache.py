"""NLI retrieval cache — session-scoped re-ranked fact/summary order.

Revision ID: zm010
Revises: zm009
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zm010"
down_revision: Union[str, Sequence[str], None] = "zm009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_retrieval_cache (
            session_id          TEXT NOT NULL,
            query_hash          TEXT NOT NULL,
            fact_ranked_ids     UUID[] NOT NULL DEFAULT '{}',
            summary_ranked_ids  UUID[] NOT NULL DEFAULT '{}',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (session_id, query_hash)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_retrieval_cache_session"
        " ON memory_retrieval_cache(session_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_retrieval_cache")
