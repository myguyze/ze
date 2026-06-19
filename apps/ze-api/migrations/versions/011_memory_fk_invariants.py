"""Add FK from memory_facts.source_episode_id → memory_episodes(id).

memory_episodes.session_id is TEXT referencing the session store by logical ID
(not a UUID FK) — that invariant is enforced at the application layer.

Revision ID: 011
Revises: 010
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, Sequence[str], None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # Migrated to ze-memory (zm005)


def downgrade() -> None:
    pass  # Migrated to ze-memory (zm005)
