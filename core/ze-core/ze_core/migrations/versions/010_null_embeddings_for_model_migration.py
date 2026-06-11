"""NULL stored embeddings after model change to paraphrase-multilingual-MiniLM-L12-v2

Embeddings in user_facts and episodes were computed with all-MiniLM-L6-v2.
The new model produces incompatible vectors for the same 384-dim column.
NULLing them ensures semantic search falls back to recency ordering until
each record is re-embedded on next write, rather than silently returning
wrong similarity scores.

news_articles embeddings are excluded — the fetch job re-embeds all articles
within 30 minutes of deployment.

Revision ID: zc010
Revises: zc009
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc010"
down_revision: Union[str, Sequence[str], None] = "zc009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE user_facts SET embedding = NULL")
    op.execute("UPDATE episodes SET embedding = NULL")


def downgrade() -> None:
    # Embeddings cannot be restored — downgrade is a no-op.
    # Re-run upgrade with the old model to rebuild.
    pass
