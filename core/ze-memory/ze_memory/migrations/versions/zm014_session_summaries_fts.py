"""FTS index on memory_session_summaries for session search.

Revision ID: zm014
Revises: zm013
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zm014"
down_revision: Union[str, Sequence[str], None] = "zm013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_session_summaries_fts_idx
            ON memory_session_summaries USING gin(
                to_tsvector('simple', coalesce(summary, ''))
            )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_session_summaries_fts_idx")
