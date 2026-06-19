"""Case-insensitive entity dedup + scoped contradiction index.

- Replaces the case-sensitive UNIQUE (canonical_name) constraint with a
  functional UNIQUE index on lower(canonical_name) so "John" and "john"
  resolve to the same entity row.
- Adds a compound index on memory_facts (predicate, subject_id) so
  contradiction checks are scoped per-subject instead of scanning all facts.

Revision ID: zm004
Revises: zm003
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm004"
down_revision: Union[str, Sequence[str], None] = "zm003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Replace case-sensitive unique constraint with a lower() functional index.
    # ON CONFLICT (lower(canonical_name)) requires a unique expression index,
    # not a constraint — so we drop the constraint and create the index.
    op.execute(
        "ALTER TABLE memory_entities"
        " DROP CONSTRAINT IF EXISTS memory_entities_canonical_name_key"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS memory_entities_canonical_name_lower_idx
            ON memory_entities (lower(canonical_name))
    """)

    # Compound index for contradiction scoping: (predicate, subject_id) lets
    # UPDATE SET contradicted=true WHERE predicate=$1 AND subject_id IS NOT
    # DISTINCT FROM $2 use an index scan instead of a seq scan.
    op.execute("""
        CREATE INDEX IF NOT EXISTS memory_facts_predicate_subject_idx
            ON memory_facts (predicate, subject_id)
            WHERE contradicted = false
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_facts_predicate_subject_idx")
    op.execute("DROP INDEX IF EXISTS memory_entities_canonical_name_lower_idx")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'memory_entities_canonical_name_key'
            ) THEN
                ALTER TABLE memory_entities
                    ADD CONSTRAINT memory_entities_canonical_name_key
                    UNIQUE (canonical_name);
            END IF;
        END $$
    """)
