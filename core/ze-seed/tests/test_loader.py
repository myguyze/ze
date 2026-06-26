from __future__ import annotations

from uuid import UUID

from ze_seed.narrative.loader import load_persona
from ze_seed.narrative.ids import (
    CONTACT_IDS,
    FACT_IDS,
    GOAL_PORTUGUESE,
    MESSAGE_IDS,
    SEED_SESSION_ID,
    SEED_THREAD_ID,
)


def test_load_persona_has_expected_counts():
    narrative = load_persona()
    assert narrative.name == "Alex"
    assert narrative.communication_style == "direct"
    assert len(narrative.facts) == 12
    assert len(narrative.episodes) == 6
    assert len(narrative.contacts) == 3
    assert len(narrative.reminders) == 2
    assert len(narrative.messages) == 8


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
    assert len(linked) == 1
    assert linked[0].source_episode_id == UUID("00000007-0001-4000-8000-000000000001")


def test_namespace_constants():
    assert SEED_SESSION_ID == "seed-dev-main"
    assert SEED_THREAD_ID == "seed-dev-chat"
    assert GOAL_PORTUGUESE in {g for g in [GOAL_PORTUGUESE]}
    assert len(CONTACT_IDS) == 3
    assert len(MESSAGE_IDS) == 8
