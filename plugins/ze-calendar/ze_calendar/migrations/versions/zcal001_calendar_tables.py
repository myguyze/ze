"""Calendar reminders and user reminders tables.

Revision ID: zcal001
Revises:
Branch labels: ze_calendar
Depends on:
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zcal001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_calendar",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS calendar_reminders (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id    TEXT        NOT NULL,
            event_title TEXT        NOT NULL,
            fire_at     TIMESTAMPTZ NOT NULL,
            label       TEXT        NOT NULL,
            assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent        BOOLEAN     NOT NULL DEFAULT false,
            sent_at     TIMESTAMPTZ
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
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_reminders (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            label      TEXT        NOT NULL,
            fire_at    TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent       BOOLEAN     NOT NULL DEFAULT false,
            sent_at    TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_reminders_unsent_idx
            ON user_reminders (fire_at)
            WHERE sent = false
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS user_reminders_unsent_idx")
    op.execute("DROP TABLE IF EXISTS user_reminders")
    op.execute("DROP INDEX IF EXISTS calendar_reminders_event_id_idx")
    op.execute("DROP INDEX IF EXISTS calendar_reminders_unsent_idx")
    op.execute("DROP TABLE IF EXISTS calendar_reminders")
