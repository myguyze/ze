from __future__ import annotations

from uuid import UUID

from ze_seed.narrative.loader import load_persona
from ze_seed.narrative.ids import (
    CONTACT_IDS,
    ENTITY_ALEX,
    ENTITY_IDS,
    FACT_IDS,
    GOAL_PORTUGUESE,
    MESSAGE_IDS,
    RELATIONSHIP_IDS,
    SEED_SESSION_ID,
    SEED_THREAD_ID,
)


def test_load_persona_has_expected_counts():
    narrative = load_persona()
    assert narrative.name == "Alex"
    assert narrative.communication_style == "direct"
    assert len(narrative.facts) == 37
    assert len(narrative.episodes) == 6
    assert len(narrative.contacts) == 4
    assert len(narrative.reminders) == 2
    assert len(narrative.messages) == 8
    assert len(narrative.entities) == 22
    assert len(narrative.relationships) == 42


def test_load_persona_fact_ids_match_manifest():
    narrative = load_persona()
    loaded_ids = {fact.id for fact in narrative.facts}
    assert loaded_ids == set(FACT_IDS)


def test_load_persona_message_with_trace():
    narrative = load_persona()
    traced = [m for m in narrative.messages if m.trace is not None]
    assert len(traced) == 4
    assert traced[0].trace is not None
    assert traced[0].trace.agent == "goals"


def test_load_persona_source_episode_link():
    narrative = load_persona()
    linked = [f for f in narrative.facts if f.source_episode_id is not None]
    assert len(linked) == 3


def test_load_persona_graph_ids_match_manifest():
    narrative = load_persona()
    assert {entity.id for entity in narrative.entities} == set(ENTITY_IDS)
    assert {rel.id for rel in narrative.relationships} == set(RELATIONSHIP_IDS)


def test_load_persona_facts_link_to_entities():
    narrative = load_persona()
    linked = [f for f in narrative.facts if f.subject_id is not None]
    assert len(linked) == 37
    entity_ids = {entity.id for entity in narrative.entities}
    assert all(fact.subject_id in entity_ids for fact in linked)


def test_load_persona_memory_variety():
    narrative = load_persona()
    unreviewed = [f for f in narrative.facts if not f.reviewed]
    contradicted = [f for f in narrative.facts if f.contradicted]
    synthesized = [f for f in narrative.facts if f.provenance == "synthesized"]
    assert len(unreviewed) == 5
    assert len(contradicted) == 1
    assert len(synthesized) == 1
    assert all(ep.summary for ep in narrative.episodes)
    assert len({ep.days_ago for ep in narrative.episodes}) > 1


def test_load_persona_graph_covers_all_entity_types():
    narrative = load_persona()
    types = {e.entity_type for e in narrative.entities}
    assert types == {"person", "place", "org", "topic"}
    by_type = {}
    for e in narrative.entities:
        by_type.setdefault(e.entity_type, []).append(e)
    assert len(by_type["person"]) == 7
    assert len(by_type["place"]) == 4
    assert len(by_type["org"]) == 2
    assert len(by_type["topic"]) == 9


def test_load_persona_alex_is_graph_hub():
    narrative = load_persona()
    alex_id = ENTITY_ALEX
    alex_edges = [
        r for r in narrative.relationships
        if r.source_id == alex_id or r.target_id == alex_id
    ]
    assert len(alex_edges) >= 12


def test_load_persona_graph_has_low_confidence_edges():
    narrative = load_persona()
    weak = [r for r in narrative.relationships if r.confidence < 0.5]
    assert len(weak) >= 2


def test_load_persona_unconfirmed_contact():
    narrative = load_persona()
    unconfirmed = [c for c in narrative.contacts if not c.confirmed]
    assert len(unconfirmed) == 1
    assert unconfirmed[0].name == "Pedro Almeida"


def test_namespace_constants():
    assert SEED_SESSION_ID == "seed-dev-main"
    assert SEED_THREAD_ID == SEED_SESSION_ID
    assert GOAL_PORTUGUESE in {g for g in [GOAL_PORTUGUESE]}
    assert len(CONTACT_IDS) == 4
    assert len(MESSAGE_IDS) == 8
