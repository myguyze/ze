"""Add push_log and calendar_reminders tables for Phase 7 proactive Ze

Revision ID: 006
Revises: 005
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_log (
            id          SERIAL PRIMARY KEY,
            event_type  TEXT NOT NULL,
            payload     TEXT,
            sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS push_log_event_type_sent_at_idx
        ON push_log (event_type, sent_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS calendar_reminders (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id     TEXT NOT NULL,
            event_title  TEXT NOT NULL,
            fire_at      TIMESTAMPTZ NOT NULL,
            label        TEXT NOT NULL,
            assessed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent         BOOLEAN NOT NULL DEFAULT false,
            sent_at      TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS calendar_reminders_unsent_idx
        ON calendar_reminders (fire_at)
        WHERE sent = false
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS calendar_reminders_event_id_idx
        ON calendar_reminders (event_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS calendar_reminders_event_id_idx")
    op.execute("DROP INDEX IF EXISTS calendar_reminders_unsent_idx")
    op.execute("DROP TABLE IF EXISTS calendar_reminders")
    op.execute("DROP INDEX IF EXISTS push_log_event_type_sent_at_idx")
    op.execute("DROP TABLE IF EXISTS push_log")
