"""notifications table for the notification center.

Revision ID: zpro002
Revises: zpro001
Branch labels: ze_proactive
Depends on:
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zpro002"
down_revision: Union[str, Sequence[str], None] = "zpro001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type  TEXT        NOT NULL,
            source      TEXT        NOT NULL,
            title       TEXT        NOT NULL,
            body        TEXT        NOT NULL,
            target_type TEXT,
            target_id   TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            read_at     TIMESTAMPTZ,
            CHECK ((target_type IS NULL) = (target_id IS NULL))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS notifications_created_at_idx
            ON notifications (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS notifications_dedup_idx
            ON notifications (event_type, target_type, target_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS notifications_unread_idx
            ON notifications (read_at) WHERE read_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS notifications_read_at_idx
            ON notifications (read_at) WHERE read_at IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS notifications_read_at_idx")
    op.execute("DROP INDEX IF EXISTS notifications_unread_idx")
    op.execute("DROP INDEX IF EXISTS notifications_dedup_idx")
    op.execute("DROP INDEX IF EXISTS notifications_created_at_idx")
    op.execute("DROP TABLE IF EXISTS notifications")
