from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def build_graph(checkpointer: Any) -> Any:
    """
    Build and compile the Ze Core orchestration graph.

    Requires langgraph to be installed. The import is deferred so the rest of
    ze_core loads without langgraph present (useful in test environments that
    only test nodes and edges individually).
    """
    from langgraph.constants import END
    from langgraph.graph import StateGraph

    from ze_core.orchestration import edges, nodes
    from ze_core.orchestration.state import AgentState

    builder = StateGraph(AgentState)

    builder.add_node("embed_route",        nodes.embed_route)
    builder.add_node("decompose",          nodes.decompose)
    builder.add_node("fetch_context",      nodes.fetch_context)
    builder.add_node("capability_check",   nodes.capability_check)
    builder.add_node("execute_tool",       nodes.execute_tool)
    builder.add_node("draft_response",     nodes.draft_response)
    builder.add_node("await_confirmation", nodes.await_confirmation)
    builder.add_node("synthesize",         nodes.synthesize)
    builder.add_node("write_memory",       nodes.write_memory)

    builder.set_entry_point("embed_route")

    builder.add_conditional_edges(
        "embed_route",
        edges.after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context"},
    )
    builder.add_edge("decompose",      "fetch_context")
    builder.add_edge("fetch_context",  "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        edges.after_capability_check,
        {"execute_tool": "execute_tool", "draft_response": "draft_response", "end_blocked": END},
    )
    builder.add_conditional_edges(
        "execute_tool",
        edges.after_execute_tool,
        {"synthesize": "synthesize", "write_memory": "write_memory"},
    )
    builder.add_edge("draft_response",     "await_confirmation")
    builder.add_edge("await_confirmation", "execute_tool")
    builder.add_edge("synthesize",         "write_memory")
    builder.add_edge("write_memory",       END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
