from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ze_agents.client import LLMClient
from ze_logging import get_logger
from ze_memory.graph.store import GraphStore

from ze_worldstate.fingerprint import compute_evidence_fingerprint
from ze_worldstate.matching import find_matching_loop
from ze_worldstate.store import LoopStore
from ze_worldstate.types import (
    EvidenceRef,
    LoopClaimKind,
    LoopProvenance,
    LoopState,
    OpenLoop,
)

log = get_logger(__name__)

DEFAULT_EXTRACTION_MODEL = "anthropic/claude-haiku-4-5"

_SUSPECTED_CONFIDENCE = 0.3
_DECLARED_CONFIDENCE = 0.9

_SYSTEM_PROMPT = """You are the relevance gate for Ze's open-loop substrate. Given a
short piece of text, decide whether it implies a genuine unfinished commitment,
task, or concern the user (or someone in their life) still needs to act on —
an "open loop" (e.g. "I need to renew my passport", "I told Maria I'd send the
contract") — OR whether it reports that a previously-open commitment is now done
(e.g. "I followed up with the accountant, it's done").

Be conservative: ordinary conversational content ("what's the weather",
"thanks!", small talk, questions) is neither.

Also decide whether the user is *explicitly declaring* the commitment themselves
("remind me I need to...", "I need to...", "I have to...") as opposed to it being
merely implied/inferred from context.

Respond with a JSON object only:
{
  "is_loop": true|false,
  "title": "short human-readable title, or empty string",
  "explicit_declaration": true|false,
  "resolves_existing": true|false
}
`resolves_existing` is true only when the text reports an existing commitment as
done/finished — in that case `is_loop` should be false and `title` is the short
description of the commitment that was resolved.
"""


class _ExtractionGateResult:
    __slots__ = ("is_loop", "title", "explicit_declaration", "resolves_existing")

    def __init__(
        self,
        is_loop: bool,
        title: str,
        explicit_declaration: bool,
        resolves_existing: bool,
    ) -> None:
        self.is_loop = is_loop
        self.title = title
        self.explicit_declaration = explicit_declaration
        self.resolves_existing = resolves_existing


async def _run_extraction_gate(
    text: str, llm_client: LLMClient, model: str
) -> _ExtractionGateResult | None:
    try:
        raw = await llm_client.complete(
            [{"role": "user", "content": text}],
            model=model,
            system=_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
    except Exception as exc:
        log.warning("loop_extraction_gate_failed", error=str(exc))
        return None

    return _ExtractionGateResult(
        is_loop=bool(parsed.get("is_loop")),
        title=str(parsed.get("title") or "").strip(),
        explicit_declaration=bool(parsed.get("explicit_declaration")),
        resolves_existing=bool(parsed.get("resolves_existing")),
    )


async def _resolve_entities(entity_resolver: Any, text: str) -> list[UUID]:
    if entity_resolver is None:
        return []
    try:
        return list(await entity_resolver(text))
    except Exception as exc:
        log.warning("loop_entity_resolution_failed", error=str(exc))
        return []


async def _link_evidence_and_entities(
    loop_id: UUID,
    evidence_refs: list[EvidenceRef],
    entity_ids: list[UUID],
    loop_store: LoopStore,
) -> None:
    for ref in evidence_refs:
        await loop_store.link_evidence(loop_id, ref.evidence_type, ref.evidence_id)
    for entity_id in entity_ids:
        await loop_store.link_entity(loop_id, entity_id)


async def _create_declared_loop(
    title: str,
    prov: LoopProvenance,
    evidence_refs: list[EvidenceRef],
    entity_ids: list[UUID],
    loop_store: LoopStore,
) -> OpenLoop:
    loop = OpenLoop(
        title=title,
        claim_kind=LoopClaimKind.PRIORITY,
        provenance=LoopProvenance.USER_DECLARED
        if prov == LoopProvenance.CONVERSATION
        else prov,
        confidence=_DECLARED_CONFIDENCE,
        state=LoopState.ACTIVE,
    )
    created = await loop_store.create(loop)
    await _link_evidence_and_entities(created.id, evidence_refs, entity_ids, loop_store)
    return created


async def propose_loop_candidates(
    text: str,
    provenance: str,
    evidence_refs: list[EvidenceRef],
    llm_client: LLMClient,
    embedder: Any,
    loop_store: LoopStore,
    entity_resolver: Any,
    *,
    graph_store: GraphStore | None = None,
    model: str = DEFAULT_EXTRACTION_MODEL,
) -> list[OpenLoop]:
    """Conservative, relevance-gated (FR-009). Returns [] for ordinary content.

    `provenance` is honoured as-is (never model narration, FR-003). Non-
    `user_declared` inflows are conservative/relevance-gated and always land
    in `suspected` at low confidence (FR-005), UNLESS the single relevance-gate
    call also classifies the text as an explicit self-declaration (FR-006) — in
    which case the loop is created directly in `active` at high confidence with
    provenance `user_declared`, bypassing matching entirely, without requiring a
    separate call-site classification step. Passing `provenance="user_declared"`
    directly (e.g. from a future non-conversational declared-loop caller) always
    takes this path too.
    """
    prov = LoopProvenance(provenance)
    entity_ids = await _resolve_entities(entity_resolver, text)

    if prov == LoopProvenance.USER_DECLARED:
        created = await _create_declared_loop(
            text.strip(), prov, evidence_refs, entity_ids, loop_store
        )
        return [created]

    gate = await _run_extraction_gate(text, llm_client, model)
    if gate is None:
        return []

    if gate.resolves_existing and gate.title and graph_store is not None:
        # T030: "it's done" recognition — resolve the matching loop instead of
        # creating a new one.
        existing = await find_matching_loop(
            entity_ids,
            gate.title,
            loop_store=loop_store,
            graph_store=graph_store,
            embedder=embedder,
            states=["suspected", "active", "drifting"],
        )
        if existing is not None:
            closed = await loop_store.transition(existing.id, LoopState.CLOSED.value)
            return [closed]
        return []

    if not gate.is_loop or not gate.title:
        return []

    if gate.explicit_declaration:
        created = await _create_declared_loop(
            gate.title, prov, evidence_refs, entity_ids, loop_store
        )
        return [created]

    fingerprint = compute_evidence_fingerprint(evidence_refs)

    if graph_store is not None:
        dismissed = await find_matching_loop(
            entity_ids,
            gate.title,
            loop_store=loop_store,
            graph_store=graph_store,
            embedder=embedder,
            states=["dropped"],
        )
        if (
            dismissed is not None
            and dismissed.dismissed_evidence_fingerprint == fingerprint
        ):
            # FR-011: don't resurface a loop from evidence the user already dismissed.
            return []

        existing = await find_matching_loop(
            entity_ids,
            gate.title,
            loop_store=loop_store,
            graph_store=graph_store,
            embedder=embedder,
            states=["suspected", "active", "drifting"],
        )
        if existing is not None:
            await _link_evidence_and_entities(
                existing.id, evidence_refs, entity_ids, loop_store
            )
            return [existing]

    loop = OpenLoop(
        title=gate.title,
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=prov,
        confidence=_SUSPECTED_CONFIDENCE,
        state=LoopState.SUSPECTED,
    )
    created = await loop_store.create(loop)
    await _link_evidence_and_entities(created.id, evidence_refs, entity_ids, loop_store)
    return [created]
