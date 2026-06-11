"""Add onboarding session, step, and seed tables.

Revision ID: 007
Revises: 006
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_sessions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            status       TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'completed', 'cancelled')),
            started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_steps (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id   UUID NOT NULL REFERENCES onboarding_sessions(id) ON DELETE CASCADE,
            plugin       TEXT NOT NULL,
            step_key     TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'active', 'completed', 'skipped')),
            descriptor   JSONB NOT NULL,
            submission   JSONB,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            UNIQUE(session_id, plugin, step_key)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_seeds (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id    UUID NOT NULL REFERENCES onboarding_sessions(id) ON DELETE CASCADE,
            step_id       UUID REFERENCES onboarding_steps(id) ON DELETE SET NULL,
            plugin        TEXT,
            kind          TEXT NOT NULL,
            key           TEXT NOT NULL,
            value         JSONB NOT NULL,
            confidence    FLOAT NOT NULL DEFAULT 1.0,
            review_status TEXT NOT NULL DEFAULT 'pending'
                          CHECK (review_status IN ('pending', 'approved', 'rejected', 'applied')),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            applied_at    TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS onboarding_sessions_status_idx
            ON onboarding_sessions (status, updated_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS onboarding_steps_session_status_idx
            ON onboarding_steps (session_id, status, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS onboarding_seeds_session_status_idx
            ON onboarding_seeds (session_id, review_status, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS onboarding_seeds_session_status_idx")
    op.execute("DROP INDEX IF EXISTS onboarding_steps_session_status_idx")
    op.execute("DROP INDEX IF EXISTS onboarding_sessions_status_idx")
    op.execute("DROP TABLE IF EXISTS onboarding_seeds")
    op.execute("DROP TABLE IF EXISTS onboarding_steps")
    op.execute("DROP TABLE IF EXISTS onboarding_sessions")
