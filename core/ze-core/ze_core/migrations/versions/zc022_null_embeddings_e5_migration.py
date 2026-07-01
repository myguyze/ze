"""Resize embedding columns from VECTOR(384) to VECTOR(768) for E5-base model.

Embeddings in user_facts and episodes were computed with
paraphrase-multilingual-MiniLM-L12-v2 (384-dim). The new E5-base model produces
768-dim vectors. Columns must be resized and HNSW indexes rebuilt. Existing
embeddings are NULLed — they will be recomputed on next write.

Revision ID: zc022
Revises: zc020
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc022"
down_revision: Union[str, Sequence[str], None] = "zc020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL first so the column type change doesn't choke on existing 384-dim data
    op.execute("UPDATE user_facts SET embedding = NULL")
    op.execute("UPDATE episodes SET embedding = NULL")

    # Drop HNSW indexes before altering column type (pgvector requirement)
    op.execute("DROP INDEX IF EXISTS user_facts_embedding_idx")
    op.execute("DROP INDEX IF EXISTS episodes_embedding_idx")

    op.execute("ALTER TABLE user_facts ALTER COLUMN embedding TYPE VECTOR(768)")
    op.execute("ALTER TABLE episodes ALTER COLUMN embedding TYPE VECTOR(768)")

    # Recreate HNSW indexes for new dimension
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_facts_embedding_idx
        ON user_facts USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_embedding_idx
        ON episodes USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
    """)


def downgrade() -> None:
    # Embeddings cannot be restored to 384-dim — downgrade is a no-op.
    pass
