"""Finance tables: accounts, positions, transactions, csv_mappings.

Revision ID: zfin001
Revises:
Branch labels: ze_finance
Depends on:
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zfin001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_finance",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_accounts (
            id              TEXT        PRIMARY KEY,
            source_id       TEXT        NOT NULL,
            account_type    TEXT        NOT NULL,
            name            TEXT        NOT NULL,
            currency        TEXT        NOT NULL,
            balance         NUMERIC     NOT NULL DEFAULT 0,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_positions (
            id              BIGSERIAL   PRIMARY KEY,
            account_id      TEXT        NOT NULL REFERENCES finance_accounts(id),
            ticker          TEXT        NOT NULL,
            asset_name      TEXT        NOT NULL,
            asset_class     TEXT        NOT NULL,
            quantity        NUMERIC     NOT NULL,
            notional        NUMERIC     NOT NULL,
            average_price   NUMERIC     NOT NULL,
            current_price   NUMERIC     NOT NULL,
            unrealised_pnl  NUMERIC     NOT NULL,
            currency        TEXT        NOT NULL,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (account_id, ticker)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_transactions (
            id              BIGSERIAL   PRIMARY KEY,
            external_id     TEXT        NOT NULL,
            account_id      TEXT        NOT NULL REFERENCES finance_accounts(id),
            transaction_type TEXT       NOT NULL,
            ticker          TEXT,
            asset_name      TEXT,
            asset_class     TEXT,
            quantity        NUMERIC     NOT NULL DEFAULT 0,
            price           NUMERIC     NOT NULL DEFAULT 0,
            fees            NUMERIC     NOT NULL DEFAULT 0,
            currency        TEXT        NOT NULL,
            settled_at      TIMESTAMPTZ NOT NULL,
            notes           TEXT        NOT NULL DEFAULT '',
            category        TEXT,
            category_source TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (account_id, external_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS finance_transactions_account_settled
            ON finance_transactions (account_id, settled_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_csv_mappings (
            source_id           TEXT        PRIMARY KEY,
            date_column         TEXT        NOT NULL,
            amount_column       TEXT,
            debit_column        TEXT,
            credit_column       TEXT,
            description_column  TEXT        NOT NULL,
            currency_column     TEXT,
            date_format         TEXT        NOT NULL,
            inferred_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS finance_transactions_account_settled")
    op.execute("DROP TABLE IF EXISTS finance_csv_mappings")
    op.execute("DROP TABLE IF EXISTS finance_transactions")
    op.execute("DROP TABLE IF EXISTS finance_positions")
    op.execute("DROP TABLE IF EXISTS finance_accounts")
