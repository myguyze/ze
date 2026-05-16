import asyncio

from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.state import AgentState
from ze.settings import Settings

log = get_logger(__name__)


async def write_memory(state: AgentState, config: dict) -> dict:
    """
    Persist the completed interaction as an episode and propose facts.
    Fires as background tasks — never blocks the graph. Runs even on error.
    """
    store: MemoryStore = config["configurable"]["memory_store"]
    ctx = state.get("agent_context")
    result = state.get("agent_result")

    if ctx is None:
        return {}

    if result is None:
        from ze.agents.types import AgentResult
        error_msg = state.get("error") or "unknown error"
        result = AgentResult(
            agent=state.get("envelope", {}).primary_agent if state.get("envelope") else "unknown",
            response=f"[ERROR] {error_msg}",
        )

    asyncio.create_task(store.write_episode(ctx, result))
    asyncio.create_task(store.propose_facts(ctx, result))

    log.debug(
        "orchestration_memory_write_scheduled",
        session_id=state["session_id"],
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

    parts = "\n\n".join(
        f"[{r.agent}]: {r.response}" for r in subtask_results
    )
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
