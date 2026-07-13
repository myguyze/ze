"""Add contacts_extracted column to episodes for ContactsConsolidator tracking.

Revision ID: zc013
Revises: zc012
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zc013"
down_revision: Union[str, Sequence[str], None] = "zc012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE episodes
            ADD COLUMN IF NOT EXISTS contacts_extracted BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_contacts_extracted_idx
            ON episodes (contacts_extracted, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS episodes_contacts_extracted_idx")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS contacts_extracted")
