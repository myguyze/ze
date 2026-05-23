"""Add contacts, contact_sources, and contact_relationships tables

Revision ID: 013
Revises: 012
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Track which episodes have been scanned for contact extraction
    op.execute("""
        ALTER TABLE episodes
        ADD COLUMN IF NOT EXISTS contacts_extracted BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS episodes_contacts_extracted_idx
            ON episodes(contacts_extracted, created_at)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name                      TEXT        NOT NULL,
            aliases                   TEXT[]      DEFAULT '{}',
            classification            TEXT        NOT NULL DEFAULT 'unknown',
            classification_confidence FLOAT       NOT NULL DEFAULT 0.0,
            relationship_to_user      TEXT,
            contact_info              JSONB       DEFAULT '{}',
            notes                     TEXT,
            confirmed                 BOOLEAN     NOT NULL DEFAULT FALSE,
            dismissed                 BOOLEAN     NOT NULL DEFAULT FALSE,
            confidence                FLOAT       NOT NULL DEFAULT 0.0,
            first_seen                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_mentioned            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS contacts_name_fts_idx
            ON contacts USING gin(to_tsvector('english', name))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS contacts_confirmed_idx
            ON contacts(confirmed, dismissed)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_sources (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id  UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            source_type TEXT        NOT NULL,
            weight      FLOAT       NOT NULL,
            raw_context TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS contact_sources_contact_id_idx
            ON contact_sources(contact_id)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_relationships (
            id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            person_a_id              UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            person_b_id              UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            relationship_description TEXT        NOT NULL,
            confidence               FLOAT       NOT NULL DEFAULT 0.5,
            source_type              TEXT        NOT NULL,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(person_a_id, person_b_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS contact_relationships_a_idx
            ON contact_relationships(person_a_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS contact_relationships_b_idx
            ON contact_relationships(person_b_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_relationships")
    op.execute("DROP TABLE IF EXISTS contact_sources")
    op.execute("DROP TABLE IF EXISTS contacts")
