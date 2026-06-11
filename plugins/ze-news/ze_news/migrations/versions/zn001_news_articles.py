"""News articles table

Revision ID: zn001
Revises:
Create Date: 2026-06-07
Branch labels: ze_news
Depends on: zc001 (pgvector extension must be installed)
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zn001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_news",)
depends_on: Union[str, Sequence[str], None] = "zc001"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            url             TEXT        PRIMARY KEY,
            source_key      TEXT        NOT NULL,
            title           TEXT        NOT NULL,
            summary         TEXT        NOT NULL DEFAULT '',
            published_at    TIMESTAMPTZ NOT NULL,
            tags            TEXT[]      NOT NULL DEFAULT '{}',
            embedding       VECTOR(384),
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_articles_published_at
            ON news_articles (published_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_articles_source_key
            ON news_articles (source_key)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_articles_tags
            ON news_articles USING GIN (tags)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS news_articles")
