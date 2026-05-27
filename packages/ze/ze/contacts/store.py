import json
from uuid import UUID

import asyncpg

from ze.contacts.types import (
    Person,
    PersonContext,
    PersonRelationship,
    PersonSource,
    StaleFollowUpNudge,
)
from ze.logging import get_logger


def _tokens(text: str) -> int:
    return len(text) // 4


def _person_from_row(row: asyncpg.Record) -> Person:
    return Person(
        id=row["id"],
        name=row["name"],
        aliases=list(row["aliases"] or []),
        classification=row["classification"],
        classification_confidence=row["classification_confidence"],
        relationship_to_user=row["relationship_to_user"] or "",
        contact_info=dict(row["contact_info"] or {}),
        notes=row["notes"] or "",
        confirmed=row["confirmed"],
        dismissed=row["dismissed"],
        confidence=row["confidence"],
        first_seen=row["first_seen"],
        last_mentioned=row["last_mentioned"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_from_row(row: asyncpg.Record) -> PersonSource:
    return PersonSource(
        id=row["id"],
        person_id=row["contact_id"],
        source_type=row["source_type"],
        weight=row["weight"],
        raw_context=row["raw_context"] or "",
        created_at=row["created_at"],
    )


class PersonStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._log = get_logger(__name__)

    async def upsert(self, person: Person) -> Person:
        """Insert a new person or update an existing one by id."""
        async with self._pool.acquire() as conn:
            if person.id is not None:
                row = await conn.fetchrow(
                    """
                    UPDATE contacts SET
                        name                      = $2,
                        aliases                   = $3,
                        classification            = $4,
                        classification_confidence = $5,
                        relationship_to_user      = $6,
                        contact_info              = $7::jsonb,
                        notes                     = $8,
                        confirmed                 = $9,
                        dismissed                 = $10,
                        confidence                = $11,
                        last_mentioned            = NOW(),
                        updated_at                = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    person.id,
                    person.name,
                    person.aliases,
                    person.classification,
                    person.classification_confidence,
                    person.relationship_to_user or None,
                    json.dumps(person.contact_info),
                    person.notes or None,
                    person.confirmed,
                    person.dismissed,
                    person.confidence,
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO contacts (
                        name, aliases, classification, classification_confidence,
                        relationship_to_user, contact_info, notes,
                        confirmed, dismissed, confidence
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10)
                    RETURNING *
                    """,
                    person.name,
                    person.aliases,
                    person.classification,
                    person.classification_confidence,
                    person.relationship_to_user or None,
                    json.dumps(person.contact_info),
                    person.notes or None,
                    person.confirmed,
                    person.dismissed,
                    person.confidence,
                )
        result = _person_from_row(row)
        self._log.debug("person_upserted", person_id=str(result.id), name=result.name)
        return result

    async def get(self, person_id: UUID) -> Person | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM contacts WHERE id = $1", person_id
            )
        return _person_from_row(row) if row else None

    async def get_by_name(self, name: str) -> list[Person]:
        """Fuzzy name lookup — used before insertion to detect potential duplicates."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM contacts
                WHERE to_tsvector('english', name) @@ plainto_tsquery('english', $1)
                   OR name ILIKE $2
                ORDER BY confirmed DESC, confidence DESC
                """,
                name,
                f"%{name}%",
            )
        return [_person_from_row(r) for r in rows]

    async def search(self, query: str, confirmed_only: bool = True) -> list[Person]:
        """Full-text search across name, relationship, and notes."""
        async with self._pool.acquire() as conn:
            if confirmed_only:
                rows = await conn.fetch(
                    """
                    SELECT * FROM contacts
                    WHERE confirmed = true AND dismissed = false
                      AND (
                        to_tsvector('english',
                            name || ' ' ||
                            COALESCE(relationship_to_user, '') || ' ' ||
                            COALESCE(notes, '')
                        ) @@ plainto_tsquery('english', $1)
                        OR name ILIKE $2
                      )
                    ORDER BY confidence DESC, last_mentioned DESC
                    LIMIT 20
                    """,
                    query,
                    f"%{query}%",
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM contacts
                    WHERE dismissed = false
                      AND (
                        to_tsvector('english',
                            name || ' ' ||
                            COALESCE(relationship_to_user, '') || ' ' ||
                            COALESCE(notes, '')
                        ) @@ plainto_tsquery('english', $1)
                        OR name ILIKE $2
                      )
                    ORDER BY confirmed DESC, confidence DESC, last_mentioned DESC
                    LIMIT 20
                    """,
                    query,
                    f"%{query}%",
                )
        return [_person_from_row(r) for r in rows]

    async def get_pending(self) -> list[tuple[Person, list[PersonSource]]]:
        """Return unconfirmed, non-dismissed candidates with their sources."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM contacts
                WHERE confirmed = false AND dismissed = false
                ORDER BY confidence DESC, last_mentioned DESC
                """
            )
            if not rows:
                return []
            people = [_person_from_row(r) for r in rows]
            result: list[tuple[Person, list[PersonSource]]] = []
            for person in people:
                source_rows = await conn.fetch(
                    """
                    SELECT * FROM contact_sources
                    WHERE contact_id = $1
                    ORDER BY created_at DESC
                    """,
                    person.id,
                )
                result.append((person, [_source_from_row(r) for r in source_rows]))
        return result

    async def confirm(self, person_id: UUID) -> Person:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE contacts SET confirmed = true, updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                person_id,
            )
        if row is None:
            raise ValueError(f"Person {person_id} not found")
        self._log.info("person_confirmed", person_id=str(person_id))
        return _person_from_row(row)

    async def dismiss(self, person_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE contacts SET dismissed = true, updated_at = NOW() WHERE id = $1",
                person_id,
            )
        self._log.info("person_dismissed", person_id=str(person_id))

    async def add_source(self, person_id: UUID, source: PersonSource) -> None:
        """Record a new source for a person and raise their confidence if applicable."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO contact_sources (contact_id, source_type, weight, raw_context)
                VALUES ($1, $2, $3, $4)
                """,
                person_id,
                source.source_type,
                source.weight,
                source.raw_context or None,
            )
            await conn.execute(
                """
                UPDATE contacts SET
                    confidence     = GREATEST(confidence, $2),
                    last_mentioned = NOW(),
                    updated_at     = NOW()
                WHERE id = $1
                """,
                person_id,
                source.weight,
            )
        self._log.debug(
            "person_source_added",
            person_id=str(person_id),
            source_type=source.source_type,
            weight=source.weight,
        )

    async def add_relationship(self, rel: PersonRelationship) -> PersonRelationship:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO contact_relationships (
                    person_a_id, person_b_id,
                    relationship_description, confidence, source_type
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (person_a_id, person_b_id) DO UPDATE SET
                    relationship_description = EXCLUDED.relationship_description,
                    confidence               = EXCLUDED.confidence
                RETURNING *
                """,
                rel.person_a_id,
                rel.person_b_id,
                rel.relationship_description,
                rel.confidence,
                rel.source_type,
            )
        return PersonRelationship(
            id=row["id"],
            person_a_id=row["person_a_id"],
            person_b_id=row["person_b_id"],
            relationship_description=row["relationship_description"],
            confidence=row["confidence"],
            source_type=row["source_type"],
            created_at=row["created_at"],
        )

    async def get_relationships(self, person_id: UUID) -> list[PersonRelationship]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM contact_relationships
                WHERE person_a_id = $1 OR person_b_id = $1
                ORDER BY confidence DESC
                """,
                person_id,
            )
        return [
            PersonRelationship(
                id=r["id"],
                person_a_id=r["person_a_id"],
                person_b_id=r["person_b_id"],
                relationship_description=r["relationship_description"],
                confidence=r["confidence"],
                source_type=r["source_type"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def list_stale_for_follow_up(
        self, stale_days: int, limit: int
    ) -> list[StaleFollowUpNudge]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT name,
                       EXTRACT(DAY FROM NOW() - last_mentioned)::int AS days_ago
                FROM contacts
                WHERE confirmed = true
                  AND dismissed = false
                  AND last_mentioned IS NOT NULL
                  AND last_mentioned < NOW() - ($1 || ' days')::interval
                ORDER BY last_mentioned ASC
                LIMIT $2
                """,
                str(stale_days),
                limit,
            )
        return [StaleFollowUpNudge(name=r["name"], days_ago=r["days_ago"]) for r in rows]

    async def get_context(self, query: str, token_budget: int = 300) -> PersonContext:
        """Return confirmed contacts whose name/role/notes match the query."""
        people = await self.search(query, confirmed_only=True)

        result: list[Person] = []
        used = 0
        for person in people:
            text = (
                f"{person.name}: "
                f"{person.relationship_to_user} "
                f"{person.notes}"
            )
            cost = _tokens(text)
            if used + cost > token_budget:
                break
            result.append(person)
            used += cost

        return PersonContext(people=result, token_estimate=used)
