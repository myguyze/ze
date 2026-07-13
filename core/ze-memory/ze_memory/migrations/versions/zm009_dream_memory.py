"""Dream Memory — offline consolidation pipeline tables and schema extensions.

Revision ID: zm009
Revises: zm008
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zm009"
down_revision: Union[str, Sequence[str], None] = "zm008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_dream_runs (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at                  TIMESTAMPTZ NOT NULL,
            finished_at                 TIMESTAMPTZ,
            episodes_scored             INT NOT NULL DEFAULT 0,
            episodes_replayed           INT NOT NULL DEFAULT 0,
            artifacts_generated         INT NOT NULL DEFAULT 0,
            artifacts_promoted          INT NOT NULL DEFAULT 0,
            artifacts_rejected          INT NOT NULL DEFAULT 0,
            artifacts_pending           INT NOT NULL DEFAULT 0,
            sleep_pass_duration_ms      INT,
            dream_pass_duration_ms      INT,
            integration_duration_ms     INT,
            error                       TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_dream_artifacts (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id                      UUID NOT NULL REFERENCES memory_dream_runs(id) ON DELETE CASCADE,
            artifact_type               TEXT NOT NULL,
            content                     TEXT NOT NULL,
            source_episode_ids          UUID[] NOT NULL DEFAULT '{}',
            source_fact_ids             UUID[] NOT NULL DEFAULT '{}',
            support_count               INT NOT NULL DEFAULT 0,
            distinct_session_count      INT NOT NULL DEFAULT 0,
            temporal_spread_days        INT NOT NULL DEFAULT 0,
            user_asserted_source_count  INT NOT NULL DEFAULT 0,
            faithfulness_score          FLOAT,
            novelty_score               FLOAT,
            retrievable                 BOOLEAN,
            critic_a_verdict            TEXT,
            critic_a_reason             TEXT,
            critic_b_verdict            TEXT,
            critic_b_reason             TEXT,
            status                      TEXT NOT NULL DEFAULT 'pending',
            user_revised_content        TEXT,
            promoted_to                 TEXT,
            promoted_id                 UUID,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            reviewed_at                 TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dream_artifacts_run"
        " ON memory_dream_artifacts(run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dream_artifacts_status"
        " ON memory_dream_artifacts(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dream_artifacts_type"
        " ON memory_dream_artifacts(artifact_type)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_dream_journal (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id                  UUID NOT NULL REFERENCES memory_dream_runs(id),
            summary                 TEXT NOT NULL,
            episodes_processed      INT NOT NULL DEFAULT 0,
            insights_promoted       INT NOT NULL DEFAULT 0,
            procedures_extracted    INT NOT NULL DEFAULT 0,
            plan_risks_surfaced     INT NOT NULL DEFAULT 0,
            pending_review          INT NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS memory_episode_metadata (
            episode_id              UUID PRIMARY KEY REFERENCES memory_episodes(id) ON DELETE CASCADE,
            replay_score            FLOAT,
            last_replayed_at        TIMESTAMPTZ,
            replay_count            INT NOT NULL DEFAULT 0,
            retrieval_weight        FLOAT NOT NULL DEFAULT 1.0,
            provenance              TEXT NOT NULL DEFAULT 'raw',
            source                  TEXT NOT NULL DEFAULT 'ze_observed',
            has_sensitive_entity    BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_metadata_score"
        " ON memory_episode_metadata(replay_score DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_metadata_weight"
        " ON memory_episode_metadata(retrieval_weight)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_metadata_source"
        " ON memory_episode_metadata(source)"
    )

    op.execute(
        "ALTER TABLE memory_facts"
        " ADD COLUMN IF NOT EXISTS provenance TEXT NOT NULL DEFAULT 'raw'"
    )
    op.execute(
        "ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ"
    )
    op.execute("ALTER TABLE memory_facts ADD COLUMN IF NOT EXISTS dream_run_id UUID")
    op.execute(
        "ALTER TABLE memory_facts"
        " ADD COLUMN IF NOT EXISTS derived_from UUID[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE memory_facts"
        " ADD COLUMN IF NOT EXISTS corroborated BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE memory_facts"
        " ADD COLUMN IF NOT EXISTS last_corroborated_at TIMESTAMPTZ"
    )

    op.execute(
        "ALTER TABLE memory_session_summaries"
        " ADD COLUMN IF NOT EXISTS dream_artifact_ids UUID[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE memory_session_summaries"
        " ADD COLUMN IF NOT EXISTS dream_influenced BOOLEAN NOT NULL DEFAULT FALSE"
    )

    op.execute(
        "ALTER TABLE memory_entities"
        " ADD COLUMN IF NOT EXISTS sensitive BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memory_entities DROP COLUMN IF EXISTS sensitive")
    op.execute(
        "ALTER TABLE memory_session_summaries DROP COLUMN IF EXISTS dream_influenced"
    )
    op.execute(
        "ALTER TABLE memory_session_summaries DROP COLUMN IF EXISTS dream_artifact_ids"
    )
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS last_corroborated_at")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS corroborated")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS derived_from")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS dream_run_id")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS valid_until")
    op.execute("ALTER TABLE memory_facts DROP COLUMN IF EXISTS provenance")
    op.execute("DROP TABLE IF EXISTS memory_episode_metadata")
    op.execute("DROP TABLE IF EXISTS memory_dream_journal")
    op.execute("DROP TABLE IF EXISTS memory_dream_artifacts")
    op.execute("DROP TABLE IF EXISTS memory_dream_runs")
