"""Add workflow_revisions table.

Revision ID: zc026
Revises: zc025
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc026"
down_revision: Union[str, Sequence[str], None] = "zc025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE workflow_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            revision_number INT NOT NULL,
            change_type TEXT NOT NULL CHECK (change_type IN ('created', 'edited')),
            steps_before JSONB NOT NULL DEFAULT '[]'::jsonb,
            steps_after JSONB NOT NULL,
            summary TEXT NOT NULL,
            actor_source TEXT NOT NULL CHECK (actor_source IN ('agent', 'api', 'system')),
            actor_session_id TEXT,
            actor_user_message_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX workflow_revisions_workflow_rev_idx
            ON workflow_revisions (workflow_id, revision_number)
    """)
    op.execute("""
        CREATE INDEX workflow_revisions_workflow_created_idx
            ON workflow_revisions (workflow_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_revisions")
