"""Case-insensitive entity dedup + scoped contradiction index.

- Replaces the case-sensitive UNIQUE (canonical_name) constraint with a
  functional UNIQUE index on lower(canonical_name) so "John" and "john"
  resolve to the same entity row.
- Adds a compound index on memory_facts (predicate, subject_id) so
  contradiction checks are scoped per-subject instead of scanning all facts.

Revision ID: 010
Revises: 009
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, Sequence[str], None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # Migrated to ze-memory (zm004)


def downgrade() -> None:
    pass  # Migrated to ze-memory (zm004)
