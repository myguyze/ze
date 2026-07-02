"""Session search FTS indexes and title_source column.

Revision ID: zc023
Revises: zc022
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc023"
down_revision: Union[str, Sequence[str], None] = "zc022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS title_source TEXT
        CHECK (title_source IN ('user', 'generated'))
    """)
    op.execute("""
        UPDATE sessions
        SET title_source = 'user'
        WHERE title IS NOT NULL AND title_source IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_text_fts_idx
            ON messages USING gin(to_tsvector('simple', coalesce(text, '')))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS sessions_metadata_fts_idx
            ON sessions USING gin(
                to_tsvector('simple',
                    coalesce(title, '') || ' ' || coalesce(preview, '')
                )
            )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sessions_metadata_fts_idx")
    op.execute("DROP INDEX IF EXISTS messages_text_fts_idx")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS title_source")
