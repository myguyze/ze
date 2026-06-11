"""Add write-path support: event participant_names column, entity unique constraint.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # participant_names stores unresolved name strings extracted from conversation.
    # participants (existing column) is reserved for resolved Entity UUIDs.
    op.execute(
        "ALTER TABLE memory_events"
        " ADD COLUMN IF NOT EXISTS participant_names JSONB NOT NULL DEFAULT '[]'::jsonb"
    )

    # Unique constraint on canonical_name enables ON CONFLICT upserts in upsert_entity.
    op.execute(
        "ALTER TABLE memory_entities"
        " ADD CONSTRAINT IF NOT EXISTS memory_entities_canonical_name_key"
        " UNIQUE (canonical_name)"
    )

    # Unique constraint on goal_id enables upsert_task_state for goal-level state.
    op.execute(
        "ALTER TABLE memory_task_state"
        " ADD CONSTRAINT IF NOT EXISTS memory_task_state_goal_id_key"
        " UNIQUE (goal_id)"
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
