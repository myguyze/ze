"""Add goal_execution_traces table and consecutive_failures/replan_count columns to goals

Revision ID: zc006
Revises: zc005
Create Date: 2026-06-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc006"
down_revision: Union[str, Sequence[str], None] = "zc005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_execution_traces (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            milestone_id UUID        NOT NULL REFERENCES goal_milestones(id) ON DELETE CASCADE,
            goal_id      UUID        NOT NULL,
            seq          INT         NOT NULL,
            tool_name    TEXT        NOT NULL,
            args         JSONB       NOT NULL DEFAULT '{}',
            result       TEXT        NOT NULL DEFAULT '',
            duration_ms  INT         NOT NULL DEFAULT 0,
            success      BOOLEAN     NOT NULL,
            error        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_execution_traces_milestone_idx
            ON goal_execution_traces(milestone_id, seq)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_execution_traces_goal_idx
            ON goal_execution_traces(goal_id, created_at DESC)
    """)
    op.execute("""
        ALTER TABLE goals ADD COLUMN IF NOT EXISTS consecutive_failures INT NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE goals ADD COLUMN IF NOT EXISTS replan_count INT NOT NULL DEFAULT 0
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS goal_execution_traces")
    op.execute("ALTER TABLE goals DROP COLUMN IF EXISTS consecutive_failures")
    op.execute("ALTER TABLE goals DROP COLUMN IF EXISTS replan_count")
