"""Add write-path support: event participant_names column, entity unique constraint.

Revision ID: zm002
Revises: zm001
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm002"
down_revision: Union[str, Sequence[str], None] = "zm001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # participant_names stores unresolved name strings extracted from conversation.
    # participants (existing column) is reserved for resolved Entity UUIDs.
    op.execute(
        "ALTER TABLE memory_events"
        " ADD COLUMN IF NOT EXISTS participant_names JSONB NOT NULL DEFAULT '[]'::jsonb"
    )

    # Unique constraint on canonical_name enables ON CONFLICT upserts in upsert_entity.
    op.execute(
        """
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
        """
    )

    # Unique constraint on goal_id enables upsert_task_state for goal-level state.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'memory_task_state_goal_id_key'
            ) THEN
                ALTER TABLE memory_task_state
                    ADD CONSTRAINT memory_task_state_goal_id_key
                    UNIQUE (goal_id);
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE memory_task_state"
        " DROP CONSTRAINT IF EXISTS memory_task_state_goal_id_key"
    )
    op.execute(
        "ALTER TABLE memory_entities"
        " DROP CONSTRAINT IF EXISTS memory_entities_canonical_name_key"
    )
    op.execute("ALTER TABLE memory_events DROP COLUMN IF EXISTS participant_names")
