"""LLM cost tracking table

Revision ID: 008
Revises: 007
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_cost_log (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id        TEXT,
            agent             TEXT        NOT NULL,
            flow_type         TEXT        NOT NULL,
            model             TEXT        NOT NULL,
            prompt_tokens     INT         NOT NULL,
            completion_tokens INT         NOT NULL,
            total_tokens      INT         NOT NULL,
            cost_usd          NUMERIC(12,8),
            duration_ms       INT         NOT NULL,
            generation_id     TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS llm_cost_log_created_idx ON llm_cost_log (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS llm_cost_log_flow_idx    ON llm_cost_log (flow_type, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS llm_cost_log_agent_idx   ON llm_cost_log (agent, created_at DESC)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS llm_cost_log_session_idx
        ON llm_cost_log (session_id)
        WHERE session_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_cost_log")
