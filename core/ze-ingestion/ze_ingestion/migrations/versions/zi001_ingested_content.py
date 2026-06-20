"""ingested_content table.

Revision ID: zi001
Revises:
Branch labels: ze_ingestion
Depends on:
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zi001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_ingestion",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingested_content (
            id              TEXT        PRIMARY KEY,
            source_url      TEXT,
            content_type    TEXT        NOT NULL,
            raw_text        TEXT        NOT NULL,
            summary         TEXT,
            facts           JSONB       NOT NULL DEFAULT '[]',
            entities        JSONB       NOT NULL DEFAULT '[]',
            tags            JSONB       NOT NULL DEFAULT '[]',
            metadata        JSONB       NOT NULL DEFAULT '{}',
            ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ingested_content_type_idx
            ON ingested_content (content_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ingested_content_at_idx
            ON ingested_content (ingested_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ingested_content_at_idx")
    op.execute("DROP INDEX IF EXISTS ingested_content_type_idx")
    op.execute("DROP TABLE IF EXISTS ingested_content")
