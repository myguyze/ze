"""Ze application schema

Squashed migration covering all Ze-specific tables.
Ze-core tables (user_facts, episodes, user_profile, routing_log,
llm_cost_log, goals/milestones/gates/learnings, persona_state,
capability_overrides) are managed by ze-core migrations zc001-zc004.

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

    # Workflow definitions and execution history.
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT        NOT NULL UNIQUE,
            description TEXT        NOT NULL,
            steps       JSONB       NOT NULL,
            schedule    TEXT,
            enabled     BOOLEAN     NOT NULL DEFAULT TRUE,
            last_run_at TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id  UUID        REFERENCES workflows(id) ON DELETE CASCADE,
            status       TEXT        NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            step_results JSONB       NOT NULL DEFAULT '[]',
            error        TEXT,
            started_at   TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS workflow_executions_workflow_id_idx
            ON workflow_executions (workflow_id, created_at DESC)
    """)

    # Proactive push log and calendar reminders.
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_log (
            id         SERIAL      PRIMARY KEY,
            event_type TEXT        NOT NULL,
            payload    TEXT,
            sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS push_log_event_type_sent_at_idx
            ON push_log (event_type, sent_at DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS calendar_reminders (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            event_id    TEXT        NOT NULL,
            event_title TEXT        NOT NULL,
            fire_at     TIMESTAMPTZ NOT NULL,
            label       TEXT        NOT NULL,
            assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent        BOOLEAN     NOT NULL DEFAULT false,
            sent_at     TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS calendar_reminders_unsent_idx
            ON calendar_reminders (fire_at)
            WHERE sent = false
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS calendar_reminders_event_id_idx
            ON calendar_reminders (event_id)
    """)

    # Weekly insight records.
    op.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            text       TEXT        NOT NULL,
            category   TEXT        NOT NULL,
            week_of    DATE        NOT NULL,
            pushed     BOOLEAN     NOT NULL DEFAULT false,
            pushed_at  TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS insights_week_of_idx
            ON insights (week_of DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS insights_category_pushed_idx
            ON insights (category, pushed_at DESC)
            WHERE pushed = true
    """)

    # One-off time-based reminders.
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_reminders (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            label      TEXT        NOT NULL,
            fire_at    TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent       BOOLEAN     NOT NULL DEFAULT false,
            sent_at    TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS user_reminders_unsent_idx
            ON user_reminders (fire_at)
            WHERE sent = false
    """)

    # Ze-specific column on ze-core's episodes table: tracks which episodes have
    # had contacts extracted by ContactsConsolidator.
    op.execute("""
        ALTER TABLE episodes
            ADD COLUMN IF NOT EXISTS contacts_extracted BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_contacts_extracted_idx
            ON episodes (contacts_extracted, created_at)
    """)

    # Prospecting: outreach campaigns and per-contact outreach records.
    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_campaigns (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            brief        TEXT        NOT NULL,
            status       TEXT        NOT NULL DEFAULT 'running',
            target_count INT,
            found_count  INT         NOT NULL DEFAULT 0,
            output       TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS prospect_campaigns_status_idx
            ON prospect_campaigns (status, created_at DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS prospect_outreach (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID        REFERENCES prospect_campaigns(id) ON DELETE CASCADE,
            contact_id  UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            channel     TEXT        NOT NULL,
            status      TEXT        NOT NULL DEFAULT 'pending',
            draft       TEXT,
            sent_at     TIMESTAMPTZ,
            replied_at  TIMESTAMPTZ,
            notes       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(campaign_id, contact_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS prospect_outreach_campaign_idx
            ON prospect_outreach (campaign_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS prospect_outreach_contact_idx
            ON prospect_outreach (contact_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS prospect_outreach_status_idx
            ON prospect_outreach (status, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prospect_outreach")
    op.execute("DROP TABLE IF EXISTS prospect_campaigns")
    op.execute("DROP INDEX IF EXISTS episodes_contacts_extracted_idx")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS contacts_extracted")
    op.execute("DROP TABLE IF EXISTS user_reminders")
    op.execute("DROP INDEX IF EXISTS insights_category_pushed_idx")
    op.execute("DROP INDEX IF EXISTS insights_week_of_idx")
    op.execute("DROP TABLE IF EXISTS insights")
    op.execute("DROP INDEX IF EXISTS calendar_reminders_event_id_idx")
    op.execute("DROP INDEX IF EXISTS calendar_reminders_unsent_idx")
    op.execute("DROP TABLE IF EXISTS calendar_reminders")
    op.execute("DROP INDEX IF EXISTS push_log_event_type_sent_at_idx")
    op.execute("DROP TABLE IF EXISTS push_log")
    op.execute("DROP INDEX IF EXISTS workflow_executions_workflow_id_idx")
    op.execute("DROP TABLE IF EXISTS workflow_executions")
    op.execute("DROP TABLE IF EXISTS workflows")
    op.execute("DROP TABLE IF EXISTS checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations")
