from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_logging import get_logger
from ze_agents.tasks import fire_and_forget
from ze_core.orchestration.nodes.context import SESSION_HISTORY_LIMIT
from ze_core.orchestration.nodes.correlation import _format_text_section
from ze_core.orchestration.state import AgentState
from ze_agents.types import AgentResult

log = get_logger(__name__)


async def write_memory(state: AgentState, config: RunnableConfig) -> dict:
    store: Any = config["configurable"]["memory_store"]
    embedder: Any = config["configurable"]["embedder"]
    ctx = state.get("agent_context")

    if ctx is None:
        return {}

    thread_id: str = config["configurable"].get("thread_id", "")
    is_eval = thread_id.startswith("eval-")

    result: AgentResult | None = state.get("agent_result")
    subtask_results: list[AgentResult] = state.get("subtask_results") or []
    final_response = state.get("final_response")

    if result is None:
        envelope = state.get("envelope")
        agent_name = envelope.primary_agent if envelope else "unknown"
        if final_response:
            all_proposals = [p for sr in subtask_results for p in sr.memory_proposals]
            result = AgentResult(agent=agent_name, response=final_response, memory_proposals=all_proposals)
        else:
            error_msg = state.get("error") or "unknown error"
            result = AgentResult(agent=agent_name, response=f"[ERROR] {error_msg}")

    if not is_eval:
        embedding = embedder.encode(ctx.prompt)
        fire_and_forget(
            store.write_episode(
                session_id=ctx.session_id,
                agent=result.agent,
                prompt=ctx.prompt,
                response=result.response,
                embedding=embedding,
            ),
            label="write_episode",
        )
        fact_extractor = config["configurable"].get("fact_extractor")
        proposals = []
        if fact_extractor is not None:
            proposals = await fact_extractor(
                config["configurable"],
                agent=result.agent,
                prompt=ctx.prompt,
                response=result.response,
                explicit=result.memory_proposals,
            )
        if proposals:
            await store.propose_facts(proposals)

        event_extractor = config["configurable"].get("event_extractor")
        if event_extractor is not None:
            events = await event_extractor(
                config["configurable"],
                prompt=ctx.prompt,
                response=result.response,
            )
            if events:
                fire_and_forget(store.propose_events(events), label="propose_events")

        entity_extractor = config["configurable"].get("entity_extractor")
        if entity_extractor is not None:
            entities = await entity_extractor(
                config["configurable"],
                prompt=ctx.prompt,
                response=result.response,
            )
            for entity in entities:
                fire_and_forget(
                    store.upsert_entity(entity),
                    label=f"upsert_entity:{entity.canonical_name}",
                )

        for hook in config["configurable"].get("memory_hooks", []):
            fire_and_forget(hook(result, ctx, config), label="memory_hook")

    log.debug(
        "orchestration_memory_write_scheduled",
        session_id=state["session_id"],
        explicit_proposals=len(result.memory_proposals) if not is_eval else 0,
        eval=is_eval,
    )

    if state.get("input_modality") == "image":
        user_content = f"[Image] {state.get('image_caption') or ''}"
    else:
        user_content = ctx.prompt

    current = list(state.get("messages") or [])
    updated = current + [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": result.response},
    ]
    return {"messages": updated[-SESSION_HISTORY_LIMIT:]}


async def synthesize(state: AgentState, config: RunnableConfig) -> dict:
    from ze_core.telemetry.context import set_agent_context
    set_agent_context("synthesis")

    client: Any = config["configurable"]["openrouter_client"]
    cfg: Any = config["configurable"].get("settings")

    synthesis_model = "anthropic/claude-haiku-4-5"
    if cfg is not None:
        models = cfg.get("models", {}) if isinstance(cfg, dict) else getattr(cfg, "config", {}).get("models", {})
        synthesis_model = models.get("synthesis", synthesis_model)

    subtask_results = state.get("subtask_results") or []
    if not subtask_results:
        return {}

    parts = "\n\n".join(f"[{r.agent}]: {r.response}" for r in subtask_results)
    synthesis_prompt = (
        "The following are responses from multiple agents for a compound user request.\n"
        "Synthesize them into a single, coherent, well-structured response.\n\n"
        f"User request: {state['prompt']}\n\n"
        f"Agent responses:\n{parts}"
    )

    response = await client.complete(
        messages=[{"role": "user", "content": synthesis_prompt}],
        model=synthesis_model,
    )
    correlations = state.get("correlations") or []
    if correlations:
        response = response + "\n\n" + _format_text_section(correlations)

    log.info(
        "orchestration_synthesis_complete",
        session_id=state["session_id"],
        subtask_count=len(subtask_results),
    )
    return {"final_response": response}


