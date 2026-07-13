"""Add session_id index to memory_episodes.

Enables efficient per-session episode queries (consolidation grouping,
session-scoped retrieval exclusions, session summaries).

Revision ID: zm007
Revises: zm006
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm007"
down_revision: Union[str, Sequence[str], None] = "zm006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS memory_episodes_session_id_idx
                ON memory_episodes (session_id, created_at DESC)
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_episodes_session_id_idx")
