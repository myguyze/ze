"""Add retrospective_text column to goals and create goal_suggestions table

Revision ID: zc007
Revises: zc006
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc007"
down_revision: Union[str, Sequence[str], None] = "zc006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE goals ADD COLUMN IF NOT EXISTS retrospective_text TEXT
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_suggestions (
            id              UUID        PRIMARY KEY,
            title           TEXT        NOT NULL,
            objective       TEXT        NOT NULL,
            rationale       TEXT        NOT NULL,
            source_type     TEXT        NOT NULL,
            source_ref      TEXT        NOT NULL,
            status          TEXT        NOT NULL DEFAULT 'pending',
            week_key        TEXT        UNIQUE,
            suggested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at     TIMESTAMPTZ,
            created_goal_id UUID        REFERENCES goals(id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_suggestions_suggested_at_idx
            ON goal_suggestions (suggested_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS goal_suggestions")
    op.execute("ALTER TABLE goals DROP COLUMN IF EXISTS retrospective_text")
