"""Add steps_snapshot to workflow_executions; allow cancelled status.

Revision ID: zc025
Revises: zc021
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc025"
down_revision: Union[str, Sequence[str], None] = "zc021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workflow_executions
          ADD COLUMN IF NOT EXISTS steps_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb
    """)
    op.execute("""
        ALTER TABLE workflow_executions
          DROP CONSTRAINT IF EXISTS workflow_executions_status_check
    """)
    op.execute("""
        ALTER TABLE workflow_executions
          ADD CONSTRAINT workflow_executions_status_check
          CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE workflow_executions
          DROP CONSTRAINT IF EXISTS workflow_executions_status_check
    """)
    op.execute("""
        ALTER TABLE workflow_executions
          ADD CONSTRAINT workflow_executions_status_check
          CHECK (status IN ('pending', 'running', 'completed', 'failed'))
    """)
    op.execute("""
        ALTER TABLE workflow_executions
          DROP COLUMN IF EXISTS steps_snapshot
    """)
