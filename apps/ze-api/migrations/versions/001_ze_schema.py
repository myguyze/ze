"""Ze application schema — LangGraph checkpoint tables.

Plugin-owned tables (memory, workflows, calendar reminders, onboarding,
prospecting, etc.) are managed by their respective package migrations.
Ze-core tables are managed by ze-core migrations zc001–zc004.

Revision ID: ze001
Revises:
Depends on: zc004 (ze-core must be fully applied first)
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "ze001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze",)
depends_on: Union[str, Sequence[str], None] = "zc004"


def upgrade() -> None:
    # LangGraph AsyncPostgresSaver checkpoint tables.
    # AsyncPostgresSaver.setup() also creates these at startup via its own
    # internal runner; all CREATE statements use IF NOT EXISTS and are safe
    # to re-execute.
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
