from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_agents.logging import get_logger
from ze_core.orchestration.state import AgentState

log = get_logger(__name__)

_DEFAULT_TAU_INLINE = 0.45
_DEFAULT_TIMEOUT_MS = 1500
_DEFAULT_MAX_SHOWN = 2
_DEFAULT_AGENTS: list[str] = ["research", "news"]


async def correlate(state: AgentState, config: RunnableConfig) -> dict:
    engine: Any = config["configurable"].get("correlation_engine")
    if engine is None:
        return {}

    envelope = state.get("envelope")
    if not envelope or not envelope.subtasks:
        return {}
    agent_name: str = envelope.subtasks[0].agent

    inline_cfg = _inline_config(config["configurable"].get("settings"))
    if agent_name not in inline_cfg["agents"]:
        return {}

    seeds = _extract_seeds(state.get("memory_context"))
    if not seeds:
        return {}

    timeout_s = inline_cfg["timeout_ms"] / 1000.0
    try:
        hypotheses = await asyncio.wait_for(
            engine.correlate(seeds, mode="inline"),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        log.info("inline_correlation_node_timeout", agent=agent_name, seeds=len(seeds))
        return {}
    except Exception as exc:
        log.warning("inline_correlation_error", agent=agent_name, error=str(exc))
        return {}

    if not hypotheses:
        return {}

    qualifying = [h for h in hypotheses if h.confidence >= inline_cfg["tau_inline"]]
    if not qualifying:
        return {}
    qualifying = qualifying[: inline_cfg["max_connections_shown"]]

    component = _build_component(qualifying)
    existing_components = list(state.get("components") or [])

    # For single-agent turns (no subtask_results), synthesize won't run — set
    # final_response here so the connections section text reaches the user.
    result = state.get("agent_result")
    is_compound = bool(envelope.is_compound and state.get("subtask_results"))
    updates: dict = {
        "correlations": qualifying,
        "components": existing_components + [component],
    }
    if not is_compound and result is not None:
        updates["final_response"] = result.response + "\n\n" + _format_text_section(qualifying)

    log.info(
        "inline_correlation_complete",
        agent=agent_name,
        hypotheses=len(qualifying),
        session_id=state.get("session_id"),
    )
    return updates


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_seeds(memory_context: Any) -> list:
    if memory_context is None:
        return []
    entities = getattr(memory_context, "entities", []) or []
    return [e.id for e in entities if e.id is not None]


def _inline_config(settings: Any) -> dict:
    raw: dict = {}
    if settings is None:
        pass
    elif isinstance(settings, dict):
        raw = settings.get("correlation", {}).get("salience", {}).get("surfacing", {})
    else:
        cfg = getattr(settings, "config", {}) or {}
        raw = cfg.get("correlation", {}).get("salience", {}).get("surfacing", {})

    inline_raw: dict = {}
    if settings is None:
        pass
    elif isinstance(settings, dict):
        inline_raw = settings.get("correlation", {}).get("inline", {})
    else:
        cfg = getattr(settings, "config", {}) or {}
        inline_raw = cfg.get("correlation", {}).get("inline", {})

    return {
        "tau_inline": float(raw.get("tau_inline", _DEFAULT_TAU_INLINE)),
        "timeout_ms": float(inline_raw.get("timeout_ms", _DEFAULT_TIMEOUT_MS)),
        "max_connections_shown": int(inline_raw.get("max_connections_shown", _DEFAULT_MAX_SHOWN)),
        "agents": list(inline_raw.get("agents", _DEFAULT_AGENTS)),
    }


def _build_component(hypotheses: list) -> dict:
    connections = []
    for h in hypotheses:
        evidence = []
        for ev in h.evidence:
            date_str: str | None = None
            ingested = getattr(ev, "ingested_at", None)
            if ingested is not None:
                if isinstance(ingested, datetime):
                    date_str = ingested.strftime("%b %d")
            evidence.append({
                "label": ev.label,
                "kind": ev.kind,
                "date": date_str,
                "source": ev.external_ref,
            })
        connections.append({
            "summary": h.summary,
            "narrative": h.narrative,
            "relation": h.relation,
            "confidence": h.confidence,
            "evidence": evidence,
        })
    return {
        "type": "connections",
        "title": "Connected to your history",
        "connections": connections,
    }


_RELATION_LABELS = {
    "pattern": "Pattern",
    "causal_guess": "Possible link",
    "tension": "Tension",
    "convergence": "Convergence",
}


def _format_text_section(hypotheses: list) -> str:
    lines = ["---", "**Connected to your history**", ""]
    for h in hypotheses:
        rel = _RELATION_LABELS.get(h.relation, h.relation)
        lines.append(f"**{rel}**: {h.summary}")
        ev_labels = ", ".join(ev.label for ev in h.evidence)
        if ev_labels:
            lines.append(f"*Sources: {ev_labels}*")
        lines.append("")
    return "\n".join(lines).rstrip()
