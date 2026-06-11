"""Add accountability_anomalies and pending_confirmations tables.

Revision ID: 006
Revises: 005
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


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

    op.execute("""
        CREATE TABLE IF NOT EXISTS pending_confirmations (
            thread_id    TEXT PRIMARY KEY,
            request_id   TEXT NOT NULL,
            prompt       TEXT NOT NULL,
            actions      JSONB NOT NULL,
            expires_at   TIMESTAMPTZ NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pending_confirmations")
    op.execute("DROP TABLE IF EXISTS accountability_anomalies")
