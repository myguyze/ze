"""push_log table for proactive job delivery tracking.

Revision ID: zpro001
Revises:
Branch labels: ze_proactive
Depends on:
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zpro001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_proactive",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_log (
            id         SERIAL      PRIMARY KEY,
            event_type TEXT        NOT NULL,
            payload    TEXT,
            sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS push_log_event_type_sent_at_idx
            ON push_log (event_type, sent_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS push_log_event_type_sent_at_idx")
    op.execute("DROP TABLE IF EXISTS push_log")
