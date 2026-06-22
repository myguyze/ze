"""End-to-end wiring tests for ZePlugin extension hooks."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from ze_plugin.plugin import ZePlugin
from ze_core.checkpoint_serde import build_checkpoint_serde, collect_checkpoint_allowlist
from ze_core.orchestration.graph import build_graph
from ze_memory.policies import CompanionPolicy, build_policy_registry
from ze_automation.workflow.types import WorkflowStep


class _StubPlugin(ZePlugin):
    depends_on: tuple[str, ...] = ()

    def checkpoint_serde_modules(self) -> tuple[str, ...]:
        return ("ze_automation.workflow.types",)

    def memory_policies(self) -> dict:
        return {"stub_agent": CompanionPolicy()}


def test_plugin_hooks_feed_checkpoint_serde_memory_registry_and_graph() -> None:
    plugins = [_StubPlugin()]

    registry = build_policy_registry(plugins)
    assert registry.for_module("stub_agent") is not None

    allowlist = set(collect_checkpoint_allowlist(plugins))
    assert ("ze_automation.workflow.types", "WorkflowStep") in allowlist
    assert ("ze_agents.types", "AgentResult") in allowlist

    serde = build_checkpoint_serde(plugins)
    step_type, _ = serde.dumps_typed(WorkflowStep(task="hello"))
    assert step_type == "msgpack"

    graph = build_graph(MemorySaver(), plugins=plugins)
    assert graph is not None
