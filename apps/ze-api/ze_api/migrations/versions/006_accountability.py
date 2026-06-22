"""Add pending_confirmations table.

Revision ID: 006
Revises: ze002
"""
from alembic import op

revision = "006"
down_revision = "ze002"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
