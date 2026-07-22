"""Add open_loops table — the open-loop substrate (Phase 109).

Revision ID: zw001
Revises:
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zw001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "zc003"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS open_loops (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title                           TEXT NOT NULL,
            state                           TEXT NOT NULL DEFAULT 'suspected',
            claim_kind                      TEXT NOT NULL,
            provenance                      TEXT NOT NULL,
            confidence                      REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
            goal_id                         UUID NULL REFERENCES goals(id),
            dismissed_evidence_fingerprint  TEXT NULL,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
            confirmed_at                    TIMESTAMPTZ NULL,
            closed_at                       TIMESTAMPTZ NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS open_loops_state_idx ON open_loops (state)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS open_loops_goal_idx ON open_loops (goal_id)"
        " WHERE goal_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS open_loops")
