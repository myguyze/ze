"""Add summary column to workflow_executions.

Revision ID: zc021
Revises: zc020
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zc021"
down_revision: Union[str, Sequence[str], None] = "zc020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS summary TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE workflow_executions DROP COLUMN IF EXISTS summary")
