"""Index memory_facts by created_at for feed pagination.

Revision ID: zm015
Revises: zm014
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zm015"
down_revision: Union[str, Sequence[str], None] = "zm014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_facts_created_at_idx
            ON memory_facts (created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_facts_created_at_idx")
