"""Add write-path support: event participant_names column, entity unique constraint.

Revision ID: 004
Revises: ze003
"""
from alembic import op

revision = "004"
down_revision = "ze003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # Migrated to ze-memory (zm002)


def downgrade() -> None:
    pass  # Migrated to ze-memory (zm002)
