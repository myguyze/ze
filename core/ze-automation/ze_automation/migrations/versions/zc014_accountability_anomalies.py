"""Move accountability_anomalies table ownership to ze-automation.

Revision ID: zc014
Revises: zc013
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zc014"
down_revision: Union[str, Sequence[str], None] = "zc013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS accountability_anomalies (
            id              BIGSERIAL PRIMARY KEY,
            agent           TEXT NOT NULL,
            run_cost_usd    NUMERIC(10, 6) NOT NULL,
            baseline_usd    NUMERIC(10, 6) NOT NULL,
            multiplier      NUMERIC(6, 2) NOT NULL,
            session_id      TEXT,
            detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_accountability_anomalies_detected_at
            ON accountability_anomalies (detected_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accountability_anomalies")
