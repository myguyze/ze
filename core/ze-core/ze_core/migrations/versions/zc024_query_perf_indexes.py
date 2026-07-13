"""Query performance indexes for cost log and activity heatmap.

Revision ID: zc024
Revises: zc023
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc024"
down_revision: Union[str, Sequence[str], None] = "zc023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS llm_cost_log_created_at_idx
            ON llm_cost_log (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_assistant_trace_created_at_idx
            ON messages (created_at)
            WHERE role = 'assistant' AND trace IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_assistant_trace_created_at_idx")
    op.execute("DROP INDEX IF EXISTS llm_cost_log_created_at_idx")
