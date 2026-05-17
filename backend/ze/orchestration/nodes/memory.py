import asyncio

from sentence_transformers import SentenceTransformer

from ze.agents.types import AgentResult
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.state import AgentState
from ze.settings import Settings

log = get_logger(__name__)


async def write_memory(state: AgentState, config: dict) -> dict:
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

    if result is None:
        error_msg = state.get("error") or "unknown error"
        envelope = state.get("envelope")
        result = AgentResult(
            agent=envelope.primary_agent if envelope else "unknown",
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
        asyncio.create_task(store.propose_facts(result.memory_proposals))

    log.debug(
        "orchestration_memory_write_scheduled",
        session_id=state["session_id"],
        proposals=len(result.memory_proposals),
    )
    return {}


async def synthesize(state: AgentState, config: dict) -> dict:
    """Merge multiple subtask results into a single coherent response via Haiku."""
    from ze.openrouter.client import OpenRouterClient

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

    synthesis_model = settings.models_config.get("models", {}).get(
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
