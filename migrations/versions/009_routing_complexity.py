"""Add complexity and model_selected columns to routing_log

Revision ID: 009
Revises: 008
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE routing_log
            ADD COLUMN IF NOT EXISTS complexity     TEXT,
            ADD COLUMN IF NOT EXISTS model_selected TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE routing_log
            DROP COLUMN IF EXISTS complexity,
            DROP COLUMN IF EXISTS model_selected
    """)
