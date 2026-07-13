"""Add FK from memory_facts.source_episode_id → memory_episodes(id).

memory_episodes.session_id is TEXT referencing the session store by logical ID
(not a UUID FK) — that invariant is enforced at the application layer.

Revision ID: zm005
Revises: zm004
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm005"
down_revision: Union[str, Sequence[str], None] = "zm004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullify any dangling references before adding the constraint.
    op.execute("""
        UPDATE memory_facts
           SET source_episode_id = NULL
         WHERE source_episode_id IS NOT NULL
           AND source_episode_id NOT IN (SELECT id FROM memory_episodes)
    """)

    op.execute("""
        ALTER TABLE memory_facts
            ADD CONSTRAINT memory_facts_source_episode_id_fkey
            FOREIGN KEY (source_episode_id)
            REFERENCES memory_episodes (id)
            ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE memory_facts
            DROP CONSTRAINT IF EXISTS memory_facts_source_episode_id_fkey
    """)
