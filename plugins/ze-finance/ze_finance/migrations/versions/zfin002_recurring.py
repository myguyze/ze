"""Finance recurring expenses and staleness nudge tables.

Revision ID: zfin002
Revises: zfin001
Branch labels:
Depends on: zfin001
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zfin002"
down_revision: Union[str, Sequence[str], None] = "zfin001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_recurring (
            normalised_key   TEXT        NOT NULL,
            account_id       TEXT        NOT NULL,
            merchant_display TEXT        NOT NULL,
            amount           NUMERIC     NOT NULL,
            currency         TEXT        NOT NULL,
            interval_days    INTEGER     NOT NULL,
            category         TEXT        NOT NULL DEFAULT 'Other',
            status           TEXT        NOT NULL DEFAULT 'detected',
            first_seen_at    TIMESTAMPTZ NOT NULL,
            last_seen_at     TIMESTAMPTZ NOT NULL,
            occurrence_count INTEGER     NOT NULL DEFAULT 1,
            PRIMARY KEY (normalised_key, account_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_recurring_staleness (
            account_id    TEXT        PRIMARY KEY,
            last_nudge_at TIMESTAMPTZ NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finance_recurring_staleness")
    op.execute("DROP TABLE IF EXISTS finance_recurring")
