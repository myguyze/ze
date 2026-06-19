"""Add memory_relationships table for graph augmentation layer.

Revision ID: 005
Revises: 004
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # Migrated to ze-memory (zm003)


def downgrade() -> None:
    pass  # Migrated to ze-memory (zm003)
