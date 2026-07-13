"""Add memory_relationships table for graph augmentation layer.

Revision ID: zm003
Revises: zm002
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm003"
down_revision: Union[str, Sequence[str], None] = "zm002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_relationships (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id        UUID NOT NULL,
            source_type      TEXT NOT NULL,
            predicate        TEXT NOT NULL,
            target_id        UUID NULL,
            target_type      TEXT NULL,
            target_text      TEXT NULL,
            confidence       FLOAT NOT NULL DEFAULT 1.0,
            provenance_id    UUID NULL,
            creation_method  TEXT NOT NULL DEFAULT 'explicit',
            reviewed         BOOLEAN NOT NULL DEFAULT false,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_relationships_source_pred_idx"
        " ON memory_relationships (source_id, predicate)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_relationships_target_idx"
        " ON memory_relationships (target_id)"
    )
    # Unique constraint enables upsert semantics (ON CONFLICT).
    # NULL target_id is allowed (textual-only relationships), so we only enforce
    # uniqueness when target_id is present.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS memory_relationships_source_pred_target_idx
        ON memory_relationships (source_id, predicate, target_id)
        WHERE target_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_relationships")
