"""memory_signals table for the signal substrate.

Revision ID: zm006
Revises: zm005
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm006"
down_revision: Union[str, Sequence[str], None] = "zm005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_signals (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source       TEXT NOT NULL,
            external_ref TEXT NOT NULL,
            title        TEXT NOT NULL,
            summary      TEXT NOT NULL,
            occurred_at  TIMESTAMPTZ,
            magnitude    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            payload      JSONB NOT NULL DEFAULT '{}',
            expires_at   TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source, external_ref)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_signals_source ON memory_signals (source)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_signals_occurred ON memory_signals (occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_signals_expires ON memory_signals (expires_at) WHERE expires_at IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_signals")
