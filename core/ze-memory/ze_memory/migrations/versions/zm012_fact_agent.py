"""Add agent column to memory_facts.

Revision ID: zm012
Revises: zm011
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm012"
down_revision: Union[str, Sequence[str], None] = "zm011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE memory_facts"
        " ADD COLUMN IF NOT EXISTS agent TEXT NOT NULL DEFAULT 'unknown'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_facts_agent_idx ON memory_facts (agent)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_facts_agent_idx")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS agent")
