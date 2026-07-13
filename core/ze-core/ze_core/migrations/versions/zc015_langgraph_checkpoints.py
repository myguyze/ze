"""LangGraph checkpoint tables.

Revision ID: zc015
Revises: zc014
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc015"
down_revision: Union[str, Sequence[str], None] = "zc014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_migrations (
            v INTEGER PRIMARY KEY
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id            TEXT NOT NULL,
            checkpoint_ns        TEXT NOT NULL DEFAULT '',
            checkpoint_id        TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type                 TEXT,
            checkpoint           JSONB NOT NULL,
            metadata             JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
            thread_id     TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel       TEXT NOT NULL,
            version       TEXT NOT NULL,
            type          TEXT NOT NULL,
            blob          BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_writes (
            thread_id     TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id       TEXT NOT NULL,
            idx           INTEGER NOT NULL,
            channel       TEXT NOT NULL,
            type          TEXT,
            blob          BYTEA NOT NULL,
            task_path     TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx
            ON checkpoints (thread_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx
            ON checkpoint_blobs (thread_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx
            ON checkpoint_writes (thread_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS checkpoint_writes_thread_id_idx")
    op.execute("DROP INDEX IF EXISTS checkpoint_blobs_thread_id_idx")
    op.execute("DROP INDEX IF EXISTS checkpoints_thread_id_idx")
    op.execute("DROP TABLE IF EXISTS checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations")
