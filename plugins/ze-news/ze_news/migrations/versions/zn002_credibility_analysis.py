"""Add credibility_analysis JSONB column to news_articles

Revision ID: zn002
Revises: zn001
Create Date: 2026-06-07
Branch labels:
Depends on: zn001
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zn002"
down_revision: Union[str, Sequence[str], None] = "zn001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE news_articles
          ADD COLUMN IF NOT EXISTS credibility_analysis JSONB DEFAULT NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE news_articles
          DROP COLUMN IF EXISTS credibility_analysis
    """)
