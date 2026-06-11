"""Add goals, goal_milestones, goal_gates, goal_learnings, and persona_state tables

Revision ID: zc003
Revises: zc002
Create Date: 2026-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "zc003"
down_revision: Union[str, Sequence[str], None] = "zc002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            title             TEXT        NOT NULL,
            objective         TEXT        NOT NULL,
            success_condition TEXT        NOT NULL,
            time_horizon      TEXT        NOT NULL DEFAULT '',
            status            TEXT        NOT NULL DEFAULT 'planning',
            type              TEXT        NOT NULL DEFAULT 'custom',
            learnings         TEXT        NOT NULL DEFAULT '',
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goals_status_idx ON goals(status, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_milestones (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            goal_id      UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            title        TEXT        NOT NULL,
            description  TEXT        NOT NULL,
            sequence     INT         NOT NULL,
            agent_hint   TEXT,
            intent       TEXT        NOT NULL DEFAULT 'execute',
            status       TEXT        NOT NULL DEFAULT 'pending',
            output       TEXT        NOT NULL DEFAULT '',
            completed_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(goal_id, sequence)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_milestones_goal_id_idx
            ON goal_milestones(goal_id, sequence)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_gates (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            goal_id          UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            after_sequence   INT         NOT NULL,
            title            TEXT        NOT NULL,
            status           TEXT        NOT NULL DEFAULT 'pending',
            context_summary  TEXT        NOT NULL DEFAULT '',
            plan_summary     TEXT        NOT NULL DEFAULT '',
            user_feedback    TEXT        NOT NULL DEFAULT '',
            fired_at         TIMESTAMPTZ,
            resolved_at      TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(goal_id, after_sequence)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_gates_goal_id_idx
            ON goal_gates(goal_id, after_sequence)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS goal_learnings (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            goal_id    UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            content    TEXT        NOT NULL,
            source     TEXT        NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS goal_learnings_goal_id_idx
            ON goal_learnings(goal_id, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS persona_state (
            id         SMALLINT    PRIMARY KEY DEFAULT 1
                       CONSTRAINT single_row CHECK (id = 1),
            profile    TEXT        NOT NULL DEFAULT 'default',
            dials      JSONB       NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        INSERT INTO persona_state (id) VALUES (1) ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS goal_learnings")
    op.execute("DROP TABLE IF EXISTS goal_gates")
    op.execute("DROP TABLE IF EXISTS goal_milestones")
    op.execute("DROP TABLE IF EXISTS goals")
    op.execute("DROP TABLE IF EXISTS persona_state")
