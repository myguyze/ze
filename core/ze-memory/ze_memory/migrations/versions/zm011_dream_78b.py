"""Dream Memory 78b — needs_resummary flag on session summaries; creation_method and dream_run_id on procedures.

Revision ID: zm011
Revises: zm010
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm011"
down_revision: Union[str, Sequence[str], None] = "zm010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE memory_session_summaries
            ADD COLUMN IF NOT EXISTS needs_resummary BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE memory_procedures
            ADD COLUMN IF NOT EXISTS creation_method TEXT NOT NULL DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS dream_run_id UUID
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_facts_provenance
        ON memory_facts(provenance)
        WHERE provenance = 'synthesized'
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_facts_corroborated
        ON memory_facts(corroborated)
        WHERE provenance = 'synthesized' AND corroborated = false
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memory_facts_corroborated")
    op.execute("DROP INDEX IF EXISTS idx_memory_facts_provenance")
    op.execute("ALTER TABLE memory_procedures DROP COLUMN IF EXISTS dream_run_id")
    op.execute("ALTER TABLE memory_procedures DROP COLUMN IF EXISTS creation_method")
    op.execute(
        "ALTER TABLE memory_session_summaries DROP COLUMN IF EXISTS needs_resummary"
    )
