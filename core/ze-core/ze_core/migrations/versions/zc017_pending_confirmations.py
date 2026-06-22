"""Pending confirmation replay state.

Revision ID: zc017
Revises: zc016
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc017"
down_revision: Union[str, Sequence[str], None] = "zc016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
