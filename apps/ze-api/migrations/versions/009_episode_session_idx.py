"""Add session_id index to memory_episodes.

Enables efficient per-session episode queries (consolidation grouping,
session-scoped retrieval exclusions, future session summaries).

Revision ID: 009
Revises: 008
Depends on: 008
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS memory_episodes_session_id_idx
            ON memory_episodes (session_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_episodes_session_id_idx")
