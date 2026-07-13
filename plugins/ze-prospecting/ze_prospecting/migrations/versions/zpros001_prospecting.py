"""Prospect campaigns and outreach tables.

Revision ID: zpros001
Revises:
Branch labels: ze_prospecting
Depends on: zc005
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "zpros001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("ze_prospecting",)
depends_on: Union[str, Sequence[str], None] = "zc005"


def upgrade() -> None:
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
    op.execute("DROP INDEX IF EXISTS prospect_outreach_status_idx")
    op.execute("DROP INDEX IF EXISTS prospect_outreach_contact_idx")
    op.execute("DROP INDEX IF EXISTS prospect_outreach_campaign_idx")
    op.execute("DROP TABLE IF EXISTS prospect_outreach")
    op.execute("DROP INDEX IF EXISTS prospect_campaigns_status_idx")
    op.execute("DROP TABLE IF EXISTS prospect_campaigns")
