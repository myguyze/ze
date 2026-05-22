"""Add user_reminders table for one-off time-based reminder pushes

Revision ID: 011
Revises: 010
Create Date: 2026-05-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
