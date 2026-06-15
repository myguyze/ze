"""Tests for plugin discovery topological sort in bootstrap.py."""
from __future__ import annotations

import pytest

from ze_agents.errors import AgentConfigError
from ze_agents.plugin import ZePlugin
from ze_api.bootstrap import _topological_sort


# ---------------------------------------------------------------------------
# Minimal stub plugins — no __init__ needed, just class-level depends_on
# ---------------------------------------------------------------------------

class _Alpha(ZePlugin):
    depends_on: tuple = ()


class _Beta(ZePlugin):
    depends_on: tuple = ("_Alpha",)


class _Gamma(ZePlugin):
    depends_on: tuple = ("_Beta",)


class _Delta(ZePlugin):
    depends_on: tuple = ("_Alpha",)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_deps_any_order_preserved():
    # When there are no deps the output should equal the input order.
    entries_nodeps = [("x", _Alpha), ("y", _Alpha)]
    result = _topological_sort(entries_nodeps)
    assert [e[0] for e in result] == ["x", "y"]


def test_simple_chain_alpha_before_beta():
    entries = [("b", _Beta), ("a", _Alpha)]
    result = _topological_sort(entries)
    names = [cls.__name__ for _, cls in result]
    assert names.index("_Alpha") < names.index("_Beta")


def test_three_level_chain_correct_order():
    # Reversed input: Gamma → Beta → Alpha
    entries = [("g", _Gamma), ("b", _Beta), ("a", _Alpha)]
    result = _topological_sort(entries)
    names = [cls.__name__ for _, cls in result]
    assert names.index("_Alpha") < names.index("_Beta")
    assert names.index("_Beta") < names.index("_Gamma")


def test_diamond_alpha_before_both_dependents():
    # _Beta and _Delta both depend on _Alpha
    entries = [("d", _Delta), ("b", _Beta), ("a", _Alpha)]
    result = _topological_sort(entries)
    names = [cls.__name__ for _, cls in result]
    assert names.index("_Alpha") < names.index("_Beta")
    assert names.index("_Alpha") < names.index("_Delta")


def test_shuffled_order_still_valid():
    import random

    entries = [("a", _Alpha), ("b", _Beta), ("g", _Gamma)]
    for _ in range(5):
        shuffled = list(entries)
        random.shuffle(shuffled)
        result = _topological_sort(shuffled)
        names = [cls.__name__ for _, cls in result]
        assert names.index("_Alpha") < names.index("_Beta")
        assert names.index("_Beta") < names.index("_Gamma")


def test_unknown_dep_raises_agent_config_error():
    class _Orphan(ZePlugin):
        depends_on = ("_NonExistent",)

    with pytest.raises(AgentConfigError, match="_NonExistent"):
        _topological_sort([("o", _Orphan)])


def test_cycle_raises_agent_config_error():
    class _CycleA(ZePlugin):
        depends_on: tuple = ("_CycleB",)

    class _CycleB(ZePlugin):
        depends_on: tuple = ("_CycleA",)

    with pytest.raises(AgentConfigError, match="Circular"):
        _topological_sort([("a", _CycleA), ("b", _CycleB)])


def test_self_dep_raises_agent_config_error():
    class _SelfRef(ZePlugin):
        depends_on: tuple = ("_SelfRef",)

    with pytest.raises(AgentConfigError):
        _topological_sort([("s", _SelfRef)])


def test_empty_entries_returns_empty():
    assert _topological_sort([]) == []
