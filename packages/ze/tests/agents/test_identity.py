from datetime import datetime

from ze_core.persona.identity import build_identity_block
from ze_core.memory.types import UserProfile


def make_profile(**overrides):
    defaults = dict(
        preferences="Likes brevity.",
        habits="Works mornings.",
        topics="AI and tech.",
        relationships="Has a cat.",
        goals="Ship Ze.",
        updated_at=datetime(2026, 5, 20),
        version=1,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def make_persona(**overrides):
    defaults = {"traits": ["direct", "warm"], "verbosity": "balanced", "dials": {}}
    defaults.update(overrides)
    return defaults


def test_identity_block_with_profile():
    block = build_identity_block(make_persona(), "(none)", profile=make_profile())
    assert "## Who this user is" in block
    assert "**Preferences:** Likes brevity." in block
    assert "**Goals:** Ship Ze." in block


def test_identity_block_without_profile():
    block = build_identity_block(make_persona(), "(none)", profile=None)
    assert "## Who this user is" not in block


def test_identity_block_skips_empty_sections():
    profile = make_profile(habits="", relationships="")
    block = build_identity_block(make_persona(), "(none)", profile=profile)
    assert "**Preferences:** Likes brevity." in block
    assert "**Habits:**" not in block
    assert "**Relationships:**" not in block


def test_identity_block_no_profile_section_when_all_empty():
    profile = make_profile(
        preferences="", habits="", topics="", relationships="", goals=""
    )
    block = build_identity_block(make_persona(), "(none)", profile=profile)
    assert "## Who this user is" not in block


def test_identity_block_default_profile_is_none():
    # No profile kwarg — should produce no profile section
    block = build_identity_block(make_persona(), "(none)")
    assert "## Who this user is" not in block


# ── Dial rendering ────────────────────────────────────────────────────────────

def test_low_humor_dial_emits_no_humor_clause():
    block = build_identity_block(make_persona(dials={"humor": 0.05}), "(none)")
    assert "no humor" in block


def test_high_humor_dial_emits_witty_clause():
    block = build_identity_block(make_persona(dials={"humor": 0.9}), "(none)")
    assert "openly funny" in block


def test_high_directness_dial_emits_conclusions_first_clause():
    block = build_identity_block(make_persona(dials={"directness": 1.0}), "(none)")
    assert "No preamble, no hedging" in block


def test_low_directness_dial_emits_socratic_clause():
    block = build_identity_block(make_persona(dials={"directness": 0.1}), "(none)")
    assert "Socratically" in block


def test_low_formality_dial_emits_casual_clause():
    block = build_identity_block(make_persona(dials={"formality": 0.0}), "(none)")
    assert "casual language" in block


def test_high_formality_dial_emits_formal_clause():
    block = build_identity_block(make_persona(dials={"formality": 0.95}), "(none)")
    assert "Formal and precise" in block


def test_high_depth_dial_emits_deep_clause():
    block = build_identity_block(make_persona(dials={"depth": 0.8}), "(none)")
    assert "Go deep" in block


def test_neutral_dial_emits_no_clause():
    # Values in [0.2, 0.8) are silent
    block = build_identity_block(make_persona(dials={"humor": 0.5, "directness": 0.5}), "(none)")
    assert "no humor" not in block
    assert "openly funny" not in block
    assert "Socratically" not in block
    assert "No preamble" not in block


def test_empty_dials_emits_nothing():
    block = build_identity_block(make_persona(dials={}), "(none)")
    # None of the extreme clauses should appear
    assert "no humor" not in block
    assert "Go deep" not in block


def test_multiple_extreme_dials_all_appear():
    block = build_identity_block(
        make_persona(dials={"humor": 0.05, "depth": 0.9, "formality": 0.9}),
        "(none)",
    )
    assert "no humor" in block
    assert "Go deep" in block
    assert "Formal and precise" in block


def test_persona_without_dials_key_works():
    # Legacy persona dict with no dials entry
    block = build_identity_block({"traits": ["direct"], "verbosity": "concise"}, "(none)")
    assert "Ze" in block


# ── Contacts rendering ────────────────────────────────────────────────────────

def test_contacts_block_renders_when_present():
    block = build_identity_block(
        make_persona(), "(none)", contacts_context="- João Silva: charter operator"
    )
    assert "## People this user knows" in block
    assert "João Silva" in block


def test_contacts_block_absent_when_empty():
    block = build_identity_block(make_persona(), "(none)", contacts_context="")
    assert "## People this user knows" not in block


def test_contacts_block_absent_by_default():
    block = build_identity_block(make_persona(), "(none)")
    assert "## People this user knows" not in block
