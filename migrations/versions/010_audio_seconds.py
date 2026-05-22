"""Add audio_seconds to llm_cost_log for Whisper cost attribution

Revision ID: 010
Revises: 009
Create Date: 2026-05-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_cost_log ADD COLUMN IF NOT EXISTS audio_seconds NUMERIC(10,3)")


def downgrade() -> None:
    op.execute("ALTER TABLE llm_cost_log DROP COLUMN IF EXISTS audio_seconds")
