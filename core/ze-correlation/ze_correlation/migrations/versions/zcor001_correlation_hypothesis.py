"""correlation_hypothesis table for the correlation engine.

Revision ID: zcor001
Revises:
Branch labels: ze_correlation
Depends on: zm006
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zcor001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_correlation",)
depends_on: Union[str, Sequence[str], None] = "zm006"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS correlation_hypothesis (
            id           UUID PRIMARY KEY,
            summary      TEXT NOT NULL,
            narrative    TEXT NOT NULL,
            relation     TEXT NOT NULL,
            confidence   REAL NOT NULL,
            relevance    REAL NOT NULL,
            evidence     JSONB NOT NULL,
            entities     JSONB NOT NULL,
            surfaced     BOOLEAN NOT NULL DEFAULT false,
            feedback     TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS correlation_hypothesis_created_idx"
        " ON correlation_hypothesis (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS correlation_hypothesis_surfaced_idx"
        " ON correlation_hypothesis (surfaced) WHERE surfaced = false"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS correlation_hypothesis")
