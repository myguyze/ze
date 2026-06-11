"""Add llm_cost_log table for telemetry

Revision ID: zc002
Revises: zc001
Create Date: 2025-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc002"
down_revision: Union[str, Sequence[str], None] = "zc001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_cost_log (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id        TEXT,
            agent             TEXT        NOT NULL DEFAULT 'unknown',
            flow_type         TEXT        NOT NULL DEFAULT 'unknown',
            model             TEXT        NOT NULL,
            prompt_tokens     INT         NOT NULL DEFAULT 0,
            completion_tokens INT         NOT NULL DEFAULT 0,
            total_tokens      INT         NOT NULL DEFAULT 0,
            cost_usd          FLOAT,
            duration_ms       INT         NOT NULL DEFAULT 0,
            generation_id     TEXT,
            audio_seconds     FLOAT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS llm_cost_log_session_idx
            ON llm_cost_log (session_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS llm_cost_log_reconcile_idx
            ON llm_cost_log (created_at ASC)
            WHERE cost_usd IS NULL AND generation_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_cost_log")
