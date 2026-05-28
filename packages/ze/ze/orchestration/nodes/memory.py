import asyncio

from langchain_core.runnables import RunnableConfig
from sentence_transformers import SentenceTransformer

from ze_core.orchestration.types import AgentResult
from ze_core.channels.types import ChannelHandle, ChannelType
from ze_core.contacts.channel_store import ContactChannelStore
from ze_core.contacts.types import ContactProposal, Person, PersonSource, SOURCE_WEIGHTS
from ze.logging import get_logger
from ze_core.memory.extractor import gather_fact_proposals
from ze_core.memory.postgres import PostgresMemoryStore as MemoryStore
from ze_core.orchestration.nodes.context import SESSION_HISTORY_LIMIT as _SESSION_HISTORY_LIMIT
from ze.orchestration.state import AgentState

log = get_logger(__name__)


async def write_memory(state: AgentState, config: RunnableConfig) -> dict:
    """
    Persist the completed interaction as an episode and propose any facts the
    agent flagged. Fires as background tasks — never blocks the graph.
    Runs even on error (writes an error episode for observability).
    """
    store: MemoryStore = config["configurable"]["memory_store"]
    embedder: SentenceTransformer = config["configurable"]["embedder"]
    ctx = state.get("agent_context")
    result = state.get("agent_result")

    if ctx is None:
        return {}

    final_response = state.get("final_response")
    subtask_results: list[AgentResult] = state.get("subtask_results") or []

    if result is None:
        envelope = state.get("envelope")
        agent_name = envelope.primary_agent if envelope else "unknown"
        if final_response:
            # Compound task: synthesized response is in final_response
            all_proposals = [p for sr in subtask_results for p in sr.memory_proposals]
            result = AgentResult(
                agent=agent_name,
                response=final_response,
                memory_proposals=all_proposals,
            )
        else:
            # Genuine error
            error_msg = state.get("error") or "unknown error"
            result = AgentResult(
                agent=agent_name,
                response=f"[ERROR] {error_msg}",
            )

    thread_id: str = config["configurable"].get("thread_id", "")
    is_eval = thread_id.startswith("eval-")

    if not is_eval:
        embedding = embedder.encode(ctx.prompt)

        asyncio.create_task(
            store.write_episode(
                agent=result.agent,
                prompt=ctx.prompt,
                response=result.response,
                embedding=embedding,
            )
        )

        proposals = await gather_fact_proposals(
            config["configurable"],
            agent=result.agent,
            prompt=ctx.prompt,
            response=result.response,
            explicit=result.memory_proposals,
        )
        if proposals:
            await store.propose_facts(proposals)

        person_store = config["configurable"].get("person_store")
        contact_channel_store = config["configurable"].get("contact_channel_store")
        if person_store and result.contact_proposals:
            asyncio.create_task(
                _write_contact_proposals(
                    person_store,
                    result.contact_proposals,
                    ctx.prompt,
                    contact_channel_store=contact_channel_store,
                )
            )

    log.debug(
        "orchestration_memory_write_scheduled",
        session_id=state["session_id"],
        explicit_proposals=len(result.memory_proposals) if not is_eval else 0,
        eval=is_eval,
    )

    # Append the completed turn and apply the rolling window.
    # Image turns are stored as "[Image] <caption>" to avoid persisting base64 bytes.
    if state.get("input_modality") == "image":
        user_content = f"[Image] {state.get('image_caption') or ''}"
    else:
        user_content = ctx.prompt
    current = list(state.get("messages") or [])
    updated = current + [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": result.response},
    ]
    return {"messages": updated[-_SESSION_HISTORY_LIMIT:]}


async def _write_contact_proposals(
    person_store,
    proposals: list[ContactProposal],
    prompt: str,
    contact_channel_store: ContactChannelStore | None = None,
) -> None:
    """Persist contact proposals from agents. Fires as a background task."""
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
    store: ContactChannelStore,
    contact_id,
    proposal: ContactProposal,
) -> None:
    """Write any channel handles from a contact proposal into contact_channels."""
    email_addr = proposal.contact_info.get("email", "").strip().lower()
    if email_addr:
        try:
            await store.upsert(contact_id, ChannelHandle(
                channel_type=ChannelType.EMAIL,
                handle=email_addr,
            ))
        except Exception as exc:
            log.warning("contact_channel_write_failed", contact_id=str(contact_id), error=str(exc))
