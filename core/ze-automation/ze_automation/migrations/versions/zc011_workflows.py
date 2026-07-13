"""Workflow definitions and execution history.

Revision ID: zc011
Revises: zc010
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zc011"
down_revision: Union[str, Sequence[str], None] = "zc010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT        NOT NULL UNIQUE,
            description TEXT        NOT NULL,
            steps       JSONB       NOT NULL,
            schedule    TEXT,
            enabled     BOOLEAN     NOT NULL DEFAULT TRUE,
            last_run_at TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id  UUID        REFERENCES workflows(id) ON DELETE CASCADE,
            status       TEXT        NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            step_results JSONB       NOT NULL DEFAULT '[]',
            error        TEXT,
            started_at   TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS workflow_executions_workflow_id_idx
            ON workflow_executions (workflow_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS workflow_executions_workflow_id_idx")
    op.execute("DROP TABLE IF EXISTS workflow_executions")
    op.execute("DROP TABLE IF EXISTS workflows")
