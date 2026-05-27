from __future__ import annotations

import asyncio
from typing import Any

from ze_core.errors import InvalidPromptError, RoutingError
from ze_core.logging import get_logger
from ze_core.orchestration.registry import get_enabled_agents
from ze_core.routing.complexity import ComplexityEstimator
from ze_core.routing.store import RoutingStore
from ze_core.routing.types import LLMClient, RouterConfig, RoutingEnvelope, SubTask

log = get_logger(__name__)


class EmbeddingRouter:
    def __init__(
        self,
        embedder: Any,
        openrouter_client: LLMClient,
        routing_store: RoutingStore | None = None,
        config: RouterConfig | None = None,
        estimator: ComplexityEstimator | None = None,
    ) -> None:
        self._embedder = embedder
        self._client = openrouter_client
        self._store = routing_store
        self._config = config or RouterConfig()
        self._estimator = estimator or ComplexityEstimator()

        self._agent_names: list[str] = []
        self._agent_matrix: Any = None
        self._load_agent_embeddings()

    # ── Public ────────────────────────────────────────────────────────────────

    async def route(self, prompt: str, session_id: str) -> RoutingEnvelope:
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt must not be empty")

        prompt = prompt.strip()

        if len(self._agent_names) == 1:
            envelope = self._single_agent_envelope(prompt)
        else:
            envelope = await self._score_and_route(prompt)

        if self._store is not None:
            asyncio.create_task(self._store.write_log(session_id, prompt, envelope))
        return envelope

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_agent_embeddings(self) -> None:
        enabled = get_enabled_agents()
        if not enabled:
            raise RoutingError("No enabled agents found")
        self._agent_names = sorted(enabled.keys())
        descriptions = [enabled[n].description.strip() for n in self._agent_names]
        self._agent_matrix = self._embedder.encode(descriptions)

    def _resolve_model(self, agent_name: str, complexity: str) -> str:
        enabled = get_enabled_agents()
        agent_cls = enabled.get(agent_name)
        if agent_cls is None:
            return "anthropic/claude-sonnet-4-5"
        if complexity == "simple" and agent_cls.model_simple:
            return agent_cls.model_simple
        return agent_cls.model

    def _primary_intent(self, agent_name: str) -> str:
        enabled = get_enabled_agents()
        agent_cls = enabled.get(agent_name)
        if agent_cls is None:
            return "read"
        return next(iter(getattr(agent_cls, "intent_map", {})), "read")

    def _single_agent_envelope(self, prompt: str) -> RoutingEnvelope:
        agent_name = self._agent_names[0]
        intent = self._primary_intent(agent_name)
        complexity = self._estimator.classify(prompt, intent, 1.0)
        model = self._resolve_model(agent_name, complexity)
        return RoutingEnvelope(
            primary_agent=agent_name,
            confidence=1.0,
            score_gap=0.0,
            routing_method="embedding",
            is_compound=False,
            subtasks=[SubTask(agent=agent_name, intent=intent, prompt=prompt, model=model)],
            requires_synthesis=False,
            raw_scores={agent_name: 1.0},
            complexity=complexity,
        )

    async def _score_and_route(self, prompt: str) -> RoutingEnvelope:
        prompt_vec = self._embedder.encode(prompt)
        scores: list[float] = (self._agent_matrix @ prompt_vec).tolist()
        raw_scores = dict(zip(self._agent_names, scores))

        sorted_pairs = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)
        top_agent, top_score = sorted_pairs[0]
        second_score = sorted_pairs[1][1]
        score_gap = top_score - second_score

        cfg = self._config
        if top_score < cfg.threshold or score_gap < cfg.gap_threshold:
            log.info(
                "routing_low_confidence",
                top_score=round(top_score, 3),
                score_gap=round(score_gap, 3),
                reason="below_threshold" if top_score < cfg.threshold else "low_gap",
            )
            # Signal to the graph that LLM decomposition is needed.
            # The `decompose` node owns the fallback.decompose() call.
            intent = self._primary_intent(top_agent)
            complexity = self._estimator.classify(prompt, intent, top_score)
            model = self._resolve_model(top_agent, complexity)
            return RoutingEnvelope(
                primary_agent=top_agent,
                confidence=top_score,
                score_gap=score_gap,
                routing_method="embedding",
                is_compound=True,
                subtasks=[SubTask(agent=top_agent, intent=intent, prompt=prompt, model=model)],
                requires_synthesis=False,
                raw_scores=raw_scores,
                complexity=complexity,
            )

        intent = self._primary_intent(top_agent)
        complexity = self._estimator.classify(prompt, intent, top_score)
        model = self._resolve_model(top_agent, complexity)
        return RoutingEnvelope(
            primary_agent=top_agent,
            confidence=top_score,
            score_gap=score_gap,
            routing_method="embedding",
            is_compound=False,
            subtasks=[SubTask(agent=top_agent, intent=intent, prompt=prompt, model=model)],
            requires_synthesis=False,
            raw_scores=raw_scores,
            complexity=complexity,
        )

