"""[Stub] Memory tables — migrated to ze-memory (zm001–zm003).

Revision ID: ze003
Revises: ze002
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "ze003"
down_revision: Union[str, Sequence[str], None] = "ze002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # Migrated to ze-memory (zm001-zm003)


def downgrade() -> None:
    pass  # Migrated to ze-memory (zm001-zm003)
