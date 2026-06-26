from __future__ import annotations

import json

from ze_personal.contacts.types import Person
from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids
from ze_seed.narrative.ids import CONTACT_IDS


async def _clear_personal(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "contacts", CONTACT_IDS)
        await conn.execute(
            "DELETE FROM contact_sources WHERE contact_id = ANY($1::uuid[])",
            CONTACT_IDS,
        )


async def _apply_personal(ctx: SeedContext) -> int:
    if ctx.narrative is None or ctx.person_store is None:
        return 0
    count = 0
    for contact in ctx.narrative.contacts:
        person = Person(
            id=contact.id,
            name=contact.name,
            classification=contact.classification,
            classification_confidence=0.9,
            relationship_to_user=contact.relationship_to_user,
            contact_info=contact.contact_info,
            notes=contact.notes,
            confirmed=contact.confirmed,
            confidence=0.9,
        )
        await ctx.person_store.upsert(person)
        count += 1

    if ctx.persona_store is not None:
        async with ctx.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO persona_state (id, profile, dials)
                VALUES (1, 'default', $1::jsonb)
                ON CONFLICT (id) DO UPDATE SET dials = EXCLUDED.dials
                """,
                json.dumps({"directness": 0.9, "formality": 0.2}),
            )
        count += 1

    return count


def personal_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain("personal.dev", seed_order=30, clear=_clear_personal, apply=_apply_personal),
    ]
