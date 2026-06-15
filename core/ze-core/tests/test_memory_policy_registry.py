"""Tests for plugin-contributed memory retrieval policies."""

from __future__ import annotations

import pytest

from ze_agents.errors import AgentConfigError
from ze_agents.plugin import ZePlugin
from ze_memory.policies import CompanionPolicy, build_policy_registry, collect_plugin_memory_policies


class _PluginA(ZePlugin):
    def memory_policies(self) -> dict:
        return {"agent_a": CompanionPolicy()}


class _PluginB(ZePlugin):
    def memory_policies(self) -> dict:
        return {"agent_b": CompanionPolicy()}


class _PluginDuplicate(ZePlugin):
    def memory_policies(self) -> dict:
        return {"agent_a": CompanionPolicy()}


def test_collect_plugin_memory_policies_merges_plugins() -> None:
    merged = collect_plugin_memory_policies([_PluginA(), _PluginB()])
    assert set(merged) == {"agent_a", "agent_b"}


def test_duplicate_memory_policy_raises() -> None:
    with pytest.raises(AgentConfigError, match="Duplicate memory policy"):
        collect_plugin_memory_policies([_PluginA(), _PluginDuplicate()])


def test_build_policy_registry_includes_core_and_plugin_policies() -> None:
    registry = build_policy_registry([_PluginA()])
    assert registry.for_module("agent_a") is not None
    assert registry.for_module("profile") is not None
    assert registry.for_module("tool_executor") is not None
