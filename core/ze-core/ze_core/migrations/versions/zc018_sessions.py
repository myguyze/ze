"""Chat sessions table — tracks distinct conversation threads.

Revision ID: zc018
Revises: zc017
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc018"
down_revision: Union[str, Sequence[str], None] = "zc017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT        PRIMARY KEY,
            title           TEXT,
            preview         TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS sessions_last_active_idx
            ON sessions (last_active_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_thread_id_idx
            ON messages (thread_id, created_at ASC)
            WHERE thread_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_thread_id_idx")
    op.execute("DROP INDEX IF EXISTS sessions_last_active_idx")
    op.execute("DROP TABLE IF EXISTS sessions")
