"""Add reuse_hint column to goal_milestones for cross-goal output reuse

Revision ID: zc009
Revises: zc008
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc009"
down_revision: Union[str, Sequence[str], None] = "zc008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE goal_milestones ADD COLUMN IF NOT EXISTS reuse_hint TEXT NOT NULL DEFAULT ''
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE goal_milestones DROP COLUMN IF EXISTS reuse_hint")
