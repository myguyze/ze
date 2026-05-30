from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ze_core.plugin import ZePlugin


def graph_builder(
    node_overrides: dict[str, Callable] | None = None,
    state_type: type | None = None,
) -> Any:
    """Return a fully-wired but uncompiled StateGraph.

    All standard nodes and internal edges are added. The ``embed_route``
    conditional edge is intentionally omitted so callers can extend the
    graph (e.g. add a ``plan_sequential`` node) before wiring routing.

    Pass ``node_overrides`` to replace specific nodes with application-specific
    implementations without touching LangGraph internals.

    Pass ``state_type`` to use a merged TypedDict (e.g. from ``build_state_type``)
    instead of the base ``AgentState``. Defaults to ``AgentState``.

    LangGraph imports are deferred so the rest of ze_core loads without
    langgraph present (useful in test environments).
    """
    from langgraph.constants import END
    from langgraph.graph import StateGraph

    from ze_core.orchestration import nodes
    from ze_core.orchestration.edges import after_capability_check, after_execute_tool
    from ze_core.orchestration.state import AgentState

    ov = node_overrides or {}
    builder = StateGraph(state_type or AgentState)

    builder.add_node("preprocess",         ov.get("preprocess",         nodes.preprocess))
    builder.add_node("embed_route",        ov.get("embed_route",        nodes.embed_route))
    builder.add_node("decompose",          ov.get("decompose",          nodes.decompose))
    builder.add_node("fetch_context",      ov.get("fetch_context",      nodes.fetch_context))
    builder.add_node("capability_check",   ov.get("capability_check",   nodes.capability_check))
    builder.add_node("execute_tool",       ov.get("execute_tool",       nodes.execute_tool))
    builder.add_node("draft_response",     ov.get("draft_response",     nodes.draft_response))
    builder.add_node("await_confirmation", ov.get("await_confirmation", nodes.await_confirmation))
    builder.add_node("synthesize",         ov.get("synthesize",         nodes.synthesize))
    builder.add_node("write_memory",       ov.get("write_memory",       nodes.write_memory))

    builder.set_entry_point("preprocess")
    builder.add_edge("preprocess", "embed_route")

    # embed_route and decompose routing conditionals are NOT wired here — see docstring.

    builder.add_edge("fetch_context",  "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        after_capability_check,
        {"execute_tool": "execute_tool", "draft_response": "draft_response", "end_blocked": END},
    )
    builder.add_conditional_edges(
        "execute_tool",
        after_execute_tool,
        {"synthesize": "synthesize", "write_memory": "write_memory"},
    )
    builder.add_edge("draft_response",     "await_confirmation")
    builder.add_edge("await_confirmation", "execute_tool")
    builder.add_edge("synthesize",         "write_memory")
    builder.add_edge("write_memory",       END)

    return builder


def build_graph(checkpointer: Any, plugins: list[ZePlugin] | None = None) -> Any:
    """Build and compile the standard conversation graph with plan_sequential routing."""
    from langgraph.constants import END

    from ze_core.orchestration import nodes
    from ze_core.orchestration.edges import after_decompose, after_embed_route
    from ze_core.orchestration.state import build_state_type

    state_type = build_state_type(plugins or [])
    builder = graph_builder(state_type=state_type)
    builder.add_node("plan_sequential", nodes.plan_sequential)

    builder.add_conditional_edges(
        "embed_route",
        after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context", "plan_sequential": "plan_sequential"},
    )
    builder.add_conditional_edges(
        "decompose",
        after_decompose,
        {"plan_sequential": "plan_sequential", "fetch_context": "fetch_context"},
    )
    builder.add_edge("plan_sequential", END)

    for plugin in (plugins or []):
        for name, fn in plugin.graph_nodes().items():
            builder.add_node(name, fn)
        plugin.graph_edges(builder)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )


def build_workflow_graph(checkpointer: Any, plugins: list[ZePlugin] | None = None) -> Any:
    """Build and compile the workflow execution graph."""
    from langgraph.constants import END

    from ze_core.orchestration import nodes
    from ze_core.orchestration.edges import after_capability_check_workflow, after_verify_step
    from ze_core.orchestration.state import build_state_type

    state_type = build_state_type(plugins or [])
    builder = graph_builder(state_type=state_type)

    builder.add_node("load_workflow_step", nodes.load_workflow_step)
    builder.add_node("verify_step",        nodes.verify_step)
    builder.add_node("workflow_synthesize", nodes.workflow_synthesize)
    builder.add_node("workflow_failed",    nodes.workflow_failed)

    builder.set_entry_point("load_workflow_step")

    builder.add_edge("load_workflow_step", "embed_route")
    builder.add_edge("embed_route",        "fetch_context")
    builder.add_edge("fetch_context",      "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        after_capability_check_workflow,
        {"execute_tool": "execute_tool", "workflow_failed": "workflow_failed"},
    )
    builder.add_edge("execute_tool",  "write_memory")
    builder.add_edge("write_memory",  "verify_step")
    builder.add_conditional_edges(
        "verify_step",
        after_verify_step,
        {
            "load_workflow_step":  "load_workflow_step",
            "workflow_synthesize": "workflow_synthesize",
            "workflow_failed":     "workflow_failed",
        },
    )
    builder.add_edge("workflow_synthesize", END)
    builder.add_edge("workflow_failed",     END)

    for plugin in (plugins or []):
        for name, fn in plugin.graph_nodes().items():
            builder.add_node(name, fn)
        plugin.graph_edges(builder)

    return builder.compile(checkpointer=checkpointer)
