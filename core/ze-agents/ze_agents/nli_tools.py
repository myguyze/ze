"""Shared NLI tools — agents pass nli_client via agentic_loop deps."""

from __future__ import annotations

from ze_agents.nli import NLIClient
from ze_agents.tool import ToolAccess, tool


@tool(
    access=ToolAccess.READ,
    description=(
        "Score natural-language inference between a premise and hypothesis. "
        "Returns contradiction, neutral, and entailment probabilities (0–1), "
        "or null scores when the pair is not scorable (non-Latin text)."
    ),
)
async def nli_check_entailment(
    nli_client: NLIClient,
    premise: str,
    hypothesis: str,
) -> dict[str, float | None] | None:
    scores = await nli_client.scores([(premise, hypothesis)])
    return scores[0] if scores else None


@tool(
    access=ToolAccess.READ,
    description=(
        "Measure how well evidence texts support a hypothesis (mean entailment score). "
        "Pass one or more evidence strings and the hypothesis to verify."
    ),
)
async def nli_grounding(
    nli_client: NLIClient,
    hypothesis: str,
    evidence: list[str],
) -> float:
    pairs = [(text, hypothesis) for text in evidence]
    scores = await nli_client.scores(pairs)
    return nli_client.grounding_score(hypothesis, evidence, scores=scores)
