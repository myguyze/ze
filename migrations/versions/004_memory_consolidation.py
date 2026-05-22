"""Add expires_at to user_facts and is_archive to episodes for Phase 5 consolidation

Revision ID: 004
Revises: 003
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_facts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_facts_expires_idx
        ON user_facts (expires_at) WHERE expires_at IS NOT NULL
    """)

    op.execute("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS is_archive BOOLEAN NOT NULL DEFAULT false")
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_is_archive_idx
        ON episodes (is_archive) WHERE is_archive = true
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS episodes_is_archive_idx")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS is_archive")

    op.execute("DROP INDEX IF EXISTS user_facts_expires_idx")
    op.execute("ALTER TABLE user_facts DROP COLUMN IF EXISTS expires_at")
