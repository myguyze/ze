"""Add last_stuck_alert_at column to goals for stuck-goal detection cooldown

Revision ID: zc008
Revises: zc007
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc008"
down_revision: Union[str, Sequence[str], None] = "zc007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE goals ADD COLUMN IF NOT EXISTS last_stuck_alert_at TIMESTAMPTZ
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goals_last_stuck_alert_at_idx
            ON goals (last_stuck_alert_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS goals_last_stuck_alert_at_idx")
    op.execute("ALTER TABLE goals DROP COLUMN IF EXISTS last_stuck_alert_at")
