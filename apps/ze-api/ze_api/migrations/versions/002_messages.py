"""Messages table for native app interface.

Persists every user and assistant message for app history load and
proactive message delivery when the app is backgrounded.

Revision ID: ze002
Revises: ze001
Depends on: ze001
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "ze002"
down_revision: Union[str, Sequence[str], None] = "ze001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
            text        TEXT,
            components  JSONB       NOT NULL DEFAULT '[]',
            read        BOOLEAN     NOT NULL DEFAULT FALSE,
            thread_id   TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_created_at_idx
            ON messages (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_unread_idx
            ON messages (read, created_at DESC)
            WHERE NOT read
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_unread_idx")
    op.execute("DROP INDEX IF EXISTS messages_created_at_idx")
    op.execute("DROP TABLE IF EXISTS messages")
