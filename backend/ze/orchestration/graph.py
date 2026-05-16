from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from ze.orchestration import edges
from ze.orchestration.nodes import (
    confirmation,
    context,
    execution,
    memory,
    routing,
)
from ze.orchestration.state import AgentState


def build_graph(checkpointer: AsyncPostgresSaver):
    builder = StateGraph(AgentState)

    # ── Nodes ─────────────────────────────────────────────────────────────
    builder.add_node("embed_route", routing.embed_route)
    builder.add_node("decompose", routing.decompose)
    builder.add_node("fetch_context", context.fetch_context)
    builder.add_node("capability_check", execution.capability_check)
    builder.add_node("execute_tool", execution.execute_tool)
    builder.add_node("draft_response", execution.draft_response)
    builder.add_node("await_confirmation", confirmation.await_confirmation)
    builder.add_node("synthesize", memory.synthesize)
    builder.add_node("write_memory", memory.write_memory)

    # ── Entry ─────────────────────────────────────────────────────────────
    builder.set_entry_point("embed_route")

    # ── Edges ─────────────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "embed_route",
        edges.after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context"},
    )
    builder.add_edge("decompose", "fetch_context")
    builder.add_edge("fetch_context", "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        edges.after_capability_check,
        {
            "execute_tool": "execute_tool",
            "draft_response": "draft_response",
            "end_blocked": END,
        },
    )
    builder.add_conditional_edges(
        "execute_tool",
        edges.after_execute_tool,
        {"synthesize": "synthesize", "write_memory": "write_memory"},
    )
    builder.add_edge("draft_response", "await_confirmation")
    builder.add_edge("await_confirmation", END)
    builder.add_edge("synthesize", "write_memory")
    builder.add_edge("write_memory", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
