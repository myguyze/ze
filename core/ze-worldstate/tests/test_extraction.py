from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

from ze_worldstate.extraction import propose_loop_candidates
from ze_worldstate.types import EvidenceRef, LoopProvenance, LoopState


def _llm(response: dict) -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=json.dumps(response))
    return client


def _empty_deps():
    loop_store = AsyncMock()
    loop_store.create = AsyncMock(side_effect=lambda loop: _with_id(loop))
    loop_store.list = AsyncMock(return_value=[])
    graph_store = AsyncMock()
    graph_store.list_relationships = AsyncMock(return_value=[])
    embedder = AsyncMock()
    entity_resolver = AsyncMock(return_value=[])
    return loop_store, graph_store, embedder, entity_resolver


def _with_id(loop):
    loop.id = uuid4()
    return loop


async def test_ordinary_content_returns_no_loop():
    llm = _llm({"is_loop": False, "title": ""})
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()

    result = await propose_loop_candidates(
        "what's the weather like",
        "conversation",
        [],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert result == []
    loop_store.create.assert_not_called()


async def test_conversation_creates_suspected_low_confidence():
    llm = _llm({"is_loop": True, "title": "Renew passport"})
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()

    result = await propose_loop_candidates(
        "I really need to renew my passport before the trip",
        "conversation",
        [EvidenceRef(evidence_type="episode", evidence_id=uuid4())],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert len(result) == 1
    loop = result[0]
    assert loop.state == LoopState.SUSPECTED
    assert loop.provenance == LoopProvenance.CONVERSATION
    assert loop.confidence < 0.5
    loop_store.link_evidence.assert_awaited_once()


async def test_all_four_inflow_provenances_create_suspected_loops():
    for provenance in ["conversation", "email", "calendar", "ingestion"]:
        llm = _llm({"is_loop": True, "title": "Follow up"})
        loop_store, graph_store, embedder, entity_resolver = _empty_deps()

        result = await propose_loop_candidates(
            "some triggering text",
            provenance,
            [],
            llm,
            embedder,
            loop_store,
            entity_resolver,
            graph_store=graph_store,
        )
        assert len(result) == 1
        assert result[0].provenance == LoopProvenance(provenance)
        assert result[0].state == LoopState.SUSPECTED


async def test_user_declared_creates_active_high_confidence_directly():
    llm = AsyncMock()
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()

    result = await propose_loop_candidates(
        "remind me I need to follow up with the accountant",
        "user_declared",
        [],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert len(result) == 1
    loop = result[0]
    assert loop.state == LoopState.ACTIVE
    assert loop.provenance == LoopProvenance.USER_DECLARED
    assert loop.confidence >= 0.8
    llm.complete.assert_not_called()


async def test_explicit_declaration_within_conversation_creates_active_user_declared():
    llm = _llm(
        {
            "is_loop": True,
            "title": "Follow up with the accountant",
            "explicit_declaration": True,
        }
    )
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()

    result = await propose_loop_candidates(
        "remind me I need to follow up with the accountant next week",
        "conversation",
        [],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert len(result) == 1
    loop = result[0]
    assert loop.state == LoopState.ACTIVE
    assert loop.provenance == LoopProvenance.USER_DECLARED
    assert loop.confidence >= 0.8


async def test_resolves_existing_closes_matching_loop_instead_of_creating():
    from ze_memory.graph.types import Relationship
    from ze_worldstate.types import LoopClaimKind, OpenLoop

    existing = OpenLoop(
        id=uuid4(),
        title="Follow up with the accountant",
        claim_kind=LoopClaimKind.PRIORITY,
        provenance=LoopProvenance.USER_DECLARED,
        confidence=0.9,
        state=LoopState.ACTIVE,
    )
    llm = _llm(
        {
            "is_loop": False,
            "title": "Follow up with the accountant",
            "resolves_existing": True,
        }
    )
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()
    entity_id = uuid4()
    entity_resolver.return_value = [entity_id]
    loop_store.get = AsyncMock(return_value=existing)
    loop_store.transition = AsyncMock(
        return_value=OpenLoop(
            **{**existing.__dict__, "state": LoopState.CLOSED},
        )
    )
    graph_store.list_relationships = AsyncMock(
        return_value=[
            Relationship(
                source_id=entity_id,
                source_type="entity",
                predicate="has_open_loop",
                target_id=existing.id,
                target_type="open_loop",
            )
        ]
    )

    result = await propose_loop_candidates(
        "I followed up with the accountant, it's done",
        "conversation",
        [],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert len(result) == 1
    assert result[0].state == LoopState.CLOSED
    loop_store.create.assert_not_called()
    loop_store.transition.assert_awaited_once_with(existing.id, LoopState.CLOSED.value)


async def test_duplicate_candidate_attaches_to_existing_loop_not_duplicated():
    from ze_worldstate.types import LoopClaimKind, OpenLoop

    existing = OpenLoop(
        id=uuid4(),
        title="Renew passport",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=0.3,
        state=LoopState.SUSPECTED,
    )
    llm = _llm({"is_loop": True, "title": "Renew passport"})
    loop_store, graph_store, embedder, entity_resolver = _empty_deps()
    entity_id = uuid4()
    entity_resolver.return_value = [entity_id]

    from ze_memory.graph.types import Relationship

    graph_store.list_relationships = AsyncMock(
        return_value=[
            Relationship(
                source_id=entity_id,
                source_type="entity",
                predicate="has_open_loop",
                target_id=existing.id,
                target_type="open_loop",
            )
        ]
    )
    loop_store.get = AsyncMock(return_value=existing)

    result = await propose_loop_candidates(
        "I still need to renew my passport",
        "conversation",
        [],
        llm,
        embedder,
        loop_store,
        entity_resolver,
        graph_store=graph_store,
    )
    assert len(result) == 1
    assert result[0].id == existing.id
    loop_store.create.assert_not_called()
