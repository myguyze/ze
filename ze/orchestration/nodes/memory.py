import asyncio

from langchain_core.runnables import RunnableConfig
from sentence_transformers import SentenceTransformer

from ze.agents.types import AgentResult
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.nodes.context import _SESSION_HISTORY_LIMIT
from ze.orchestration.state import AgentState
from ze.settings import Settings
from ze.telemetry.context import set_agent_context

log = get_logger(__name__)


async def write_memory(state: AgentState, config: RunnableConfig) -> dict:
    """
    Persist the completed interaction as an episode and propose any facts the
    agent flagged. Fires as background tasks — never blocks the graph.
    Runs even on error (writes an error episode for observability).
    """
    store: MemoryStore = config["configurable"]["memory_store"]
    embedder: SentenceTransformer = config["configurable"]["embedder"]
    ctx = state.get("agent_context")
    result = state.get("agent_result")

    if ctx is None:
        return {}

    final_response = state.get("final_response")
    subtask_results: list[AgentResult] = state.get("subtask_results") or []

    if result is None:
        envelope = state.get("envelope")
        agent_name = envelope.primary_agent if envelope else "unknown"
        if final_response:
            # Compound task: synthesized response is in final_response
            all_proposals = [p for sr in subtask_results for p in sr.memory_proposals]
            result = AgentResult(
                agent=agent_name,
                response=final_response,
                memory_proposals=all_proposals,
            )
        else:
            # Genuine error
            error_msg = state.get("error") or "unknown error"
            result = AgentResult(
                agent=agent_name,
                response=f"[ERROR] {error_msg}",
            )

    embedding = embedder.encode(ctx.prompt)

    asyncio.create_task(
        store.write_episode(
            agent=result.agent,
            prompt=ctx.prompt,
            response=result.response,
            embedding=embedding,
        )
    )

    if result.memory_proposals:
        await store.propose_facts(result.memory_proposals)

    log.debug(
        "orchestration_memory_write_scheduled",
        session_id=state["session_id"],
        proposals=len(result.memory_proposals),
    )

    # Append the completed turn and apply the rolling window.
    # Image turns are stored as "[Image] <caption>" to avoid persisting base64 bytes.
    if state.get("input_modality") == "image":
        user_content = f"[Image] {state.get('image_caption') or ''}"
    else:
        user_content = ctx.prompt
    current = list(state.get("messages") or [])
    updated = current + [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": result.response},
    ]
    return {"messages": updated[-_SESSION_HISTORY_LIMIT:]}


async def synthesize(state: AgentState, config: RunnableConfig) -> dict:
    """Merge multiple subtask results into a single coherent response via Haiku."""
    from ze.openrouter.client import OpenRouterClient

    set_agent_context("synthesis")
    client: OpenRouterClient = config["configurable"]["openrouter_client"]
    settings: Settings = config["configurable"]["settings"]

    subtask_results = state.get("subtask_results", [])
    if not subtask_results:
        return {}

    parts = "\n\n".join(f"[{r.agent}]: {r.response}" for r in subtask_results)
    synthesis_prompt = (
        "The following are responses from multiple agents for a compound user request.\n"
        "Synthesize them into a single, coherent, well-structured response.\n\n"
        f"User request: {state['prompt']}\n\n"
        f"Agent responses:\n{parts}"
    )

    synthesis_model = settings.config.get("models", {}).get(
        "synthesis", "anthropic/claude-haiku-4-5"
    )

    response = await client.complete(
        messages=[{"role": "user", "content": synthesis_prompt}],
        model=synthesis_model,
    )

    log.info(
        "orchestration_synthesis_complete",
        session_id=state["session_id"],
        subtask_count=len(subtask_results),
    )

    return {"final_response": response}
