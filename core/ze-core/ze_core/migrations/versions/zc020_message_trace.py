"""Add trace JSONB column to messages table.

Revision ID: zc020
Revises: zc019
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc020"
down_revision: Union[str, Sequence[str], None] = "zc019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE messages ADD COLUMN IF NOT EXISTS trace JSONB NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_trace_agent_idx
            ON messages ((trace->>'agent'))
            WHERE trace IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_trace_agent_idx")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS trace")
