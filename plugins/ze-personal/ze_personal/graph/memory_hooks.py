"""Contact extraction memory hook.

Transitional location — will move to ze_personal/graph/memory_hooks.py once
the ze-personal package is created (arch-package-reorg step 4).
"""
from __future__ import annotations

from typing import Any

from ze_core.channels.types import ChannelHandle, ChannelType
from ze_personal.contacts.types import ContactProposal, Person, PersonSource
from ze_core.logging import get_logger

log = get_logger(__name__)


async def contact_proposal_hook(result: Any, ctx: Any, config: dict) -> None:
    """Write contact proposals from an agent result into the person store.

    Reads person_store and contact_channel_store from config["configurable"].
    No-op when person_store is absent or result has no proposals.
    """
    person_store = config["configurable"].get("person_store")
    contact_channel_store = config["configurable"].get("contact_channel_store")
    if person_store and result.contact_proposals:
        await _write_contact_proposals(
            person_store,
            result.contact_proposals,
            ctx.prompt,
            contact_channel_store=contact_channel_store,
        )


async def _write_contact_proposals(
    person_store: Any,
    proposals: list[ContactProposal],
    prompt: str,
    contact_channel_store: Any = None,
) -> None:
    for proposal in proposals:
        if not proposal.name:
            continue
        try:
            existing = await person_store.get_by_name(proposal.name)
            source = PersonSource(
                person_id=None,  # type: ignore[arg-type]  — replaced below
                source_type=proposal.source_type,
                weight=proposal.confidence,
                raw_context=prompt[:300],
            )
            if existing:
                best = existing[0]
                source.person_id = best.id
                await person_store.add_source(best.id, source)
                contact_id = best.id
            else:
                person = Person(
                    name=proposal.name,
                    classification=proposal.classification,
                    classification_confidence=proposal.confidence,
                    relationship_to_user=proposal.relationship,
                    contact_info=proposal.contact_info,
                    confirmed=proposal.confirmed,
                    dismissed=False,
                    confidence=proposal.confidence,
                )
                stored = await person_store.upsert(person)
                source.person_id = stored.id
                await person_store.add_source(stored.id, source)
                contact_id = stored.id

            if contact_channel_store:
                await _write_channel_handles(contact_channel_store, contact_id, proposal)

        except Exception as exc:
            log.warning("contact_proposal_write_failed", name=proposal.name, error=str(exc))


async def _write_channel_handles(
    store: Any,
    contact_id: Any,
    proposal: ContactProposal,
) -> None:
    email_addr = proposal.contact_info.get("email", "").strip().lower()
    if email_addr:
        try:
            await store.upsert(contact_id, ChannelHandle(
                channel_type=ChannelType.EMAIL,
                handle=email_addr,
            ))
        except Exception as exc:
            log.warning("contact_channel_write_failed", contact_id=str(contact_id), error=str(exc))
