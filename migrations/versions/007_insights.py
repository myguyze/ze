"""Add insights table for Phase 8 insight generation

Revision ID: 007
Revises: 006
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            text         TEXT NOT NULL,
            category     TEXT NOT NULL,
            week_of      DATE NOT NULL,
            pushed       BOOLEAN NOT NULL DEFAULT false,
            pushed_at    TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS insights_week_of_idx
        ON insights (week_of DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS insights_category_pushed_idx
        ON insights (category, pushed_at DESC)
        WHERE pushed = true
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS insights_category_pushed_idx")
    op.execute("DROP INDEX IF EXISTS insights_week_of_idx")
    op.execute("DROP TABLE IF EXISTS insights")
