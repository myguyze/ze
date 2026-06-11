"""Add expires_at to user_facts and capability_overrides table

Revision ID: zc004
Revises: zc003
Create Date: 2026-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc004"
down_revision: Union[str, Sequence[str], None] = "zc003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Grace-period expiry: facts are soft-expired by setting expires_at,
    # then hard-deleted once the timestamp elapses.
    op.execute(
        "ALTER TABLE user_facts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS user_facts_expires_at_idx"
        " ON user_facts (expires_at) WHERE expires_at IS NOT NULL"
    )

    # Persistent capability overrides: DB-backed replacement for update_permanent().
    # Overrides survive restarts and take precedence over agent class-attribute modes.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS capability_overrides (
            agent      TEXT        NOT NULL,
            intent     TEXT        NOT NULL,
            mode       TEXT        NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (agent, intent)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS capability_overrides")
    op.execute("DROP INDEX IF EXISTS user_facts_expires_at_idx")
    op.execute("ALTER TABLE user_facts DROP COLUMN IF EXISTS expires_at")
