from uuid import UUID

from ze_core.orchestration.tool import ToolAccess, tool
from ze_personal.contacts.store import PersonStore
from ze_personal.contacts.types import Person, PersonSource
from ze_core.openrouter.client import OpenRouterClient
from ze_prospecting.store import ProspectCampaignStore

_VALID_EVENT_TYPES = frozenset({"sent", "replied", "bounced"})

_DRAFT_SYSTEM = (
    "You write concise, personalised outreach messages. "
    "Write only the message body — no subject line, no greeting, no sign-off. "
    "Tailor the message to the person's role and company based on the context provided."
)


@tool(
    access=ToolAccess.WRITE,
    description=(
        "Add a prospective contact found during research. "
        "Sets confirmed=False and source_type='research'. "
        "Call once per person found — deduplication is automatic. "
        "Set channel to 'email' or 'linkedin' based on what contact info was found."
    ),
)
async def add_prospect(
    name: str,
    company: str | None,
    role: str | None,
    relationship: str,
    contact_info: dict,
    source_url: str,
    enrichment_notes: str,
    campaign_id: str,
    channel: str = "email",
    person_store: PersonStore = None,
    campaign_store: ProspectCampaignStore = None,
) -> str:
    existing = await person_store.get_by_name(name)
    if existing:
        person = existing[0]
        await person_store.add_source(
            person.id,
            PersonSource(
                person_id=person.id,
                source_type="research",
                weight=0.2,
                raw_context=f"source: {source_url}\n{enrichment_notes}",
            ),
        )
    else:
        rel = relationship
        if company and role:
            rel = f"{role} at {company} — {relationship}"
        elif company:
            rel = f"{company} — {relationship}"
        elif role:
            rel = f"{role} — {relationship}"

        person = await person_store.upsert(
            Person(
                name=name,
                classification="professional",
                classification_confidence=0.6,
                relationship_to_user=rel,
                contact_info=contact_info or {},
                notes=enrichment_notes,
                confirmed=False,
                confidence=0.2,
            )
        )
        await person_store.add_source(
            person.id,
            PersonSource(
                person_id=person.id,
                source_type="research",
                weight=0.2,
                raw_context=f"source: {source_url}\n{enrichment_notes}",
            ),
        )

    outreach_id = await campaign_store.add_outreach(UUID(campaign_id), person.id, channel)
    if outreach_id is not None:
        await campaign_store.increment_found(UUID(campaign_id))

    return f"Added {name} (id={person.id})"


@tool(
    access=ToolAccess.WRITE,
    description="Draft a personalised outreach message for a prospect and save it.",
)
async def draft_outreach(
    name: str,
    context: str,
    campaign_brief: str,
    channel: str,
    campaign_id: str,
    client: OpenRouterClient,
    model: str,
    person_store: PersonStore,
    campaign_store: ProspectCampaignStore,
) -> str:
    matches = await person_store.get_by_name(name)
    if not matches:
        raise ValueError(f"No contact found for {name!r}")

    person = matches[0]

    prompt = (
        f"Campaign goal: {campaign_brief}\n"
        f"Prospect: {name}\n"
        f"Context: {context}\n"
        f"Channel: {channel}\n\n"
        "Write a personalised outreach message (body only, no greeting or sign-off)."
    )
    draft = await client.complete(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        system=_DRAFT_SYSTEM,
        max_tokens=400,
    )

    await campaign_store.save_draft(UUID(campaign_id), person.id, draft)

    return draft


@tool(
    access=ToolAccess.WRITE,
    description=(
        "Record that the user sent a message to a prospect or received a reply. "
        "Call when the user explicitly mentions contacting someone or getting a response."
    ),
)
async def log_outreach_event(
    contact_name: str,
    event_type: str,
    channel: str,
    notes: str,
    campaign_store: ProspectCampaignStore,
    person_store: PersonStore,
) -> str:
    if event_type not in _VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type {event_type!r} — must be one of {sorted(_VALID_EVENT_TYPES)}"
        )

    matches = await person_store.get_by_name(contact_name)

    if not matches:
        raise ValueError(f"No contact found for {contact_name!r}")

    if len(matches) > 1:
        names_str = " and ".join(m.name for m in matches[:3])
        raise ValueError(f"Ambiguous: found {names_str} — please clarify")

    person = matches[0]
    outreach_id = await campaign_store.get_latest_outreach_id(person.id)

    if outreach_id is None:
        raise ValueError(f"{contact_name} is not in any outreach campaign")

    await campaign_store.log_outreach_event(outreach_id, event_type, notes, _ts_column(event_type))

    return f"Logged {event_type} for {person.name}"


def _ts_column(event_type: str) -> str | None:
    return {"sent": "sent_at", "replied": "replied_at"}.get(event_type)
