"""Add user_channels, user_channel_watermarks, and thread_channel_map tables.

Revision ID: zc019
Revises: zc018
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zc019"
down_revision: Union[str, Sequence[str], None] = "zc018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_channels (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id        TEXT        NOT NULL UNIQUE,
            channel_type      TEXT        NOT NULL,
            handle            TEXT        NOT NULL,
            display_name      TEXT,
            is_default_outbound BOOLEAN   NOT NULL DEFAULT FALSE,
            poll_enabled      BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_channel_watermarks (
            channel_id        TEXT        PRIMARY KEY REFERENCES user_channels(channel_id),
            last_polled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS thread_channel_map (
            thread_id         TEXT        PRIMARY KEY,
            channel_id        TEXT        NOT NULL,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS thread_channel_map")
    op.execute("DROP TABLE IF EXISTS user_channel_watermarks")
    op.execute("DROP TABLE IF EXISTS user_channels")
