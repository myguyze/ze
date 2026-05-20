import asyncio
import json

import asyncpg
import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from ze.errors import InvalidPromptError, RoutingError
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.routing import haiku_fallback
from ze.routing.complexity import ComplexityEstimator
from ze.routing.types import RoutingEnvelope, SubTask
from ze.settings import Settings
from ze.telemetry.context import set_agent_context


class EmbeddingRouter:
    def __init__(
        self,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        db_pool: asyncpg.Pool,
        settings: Settings,
        estimator: ComplexityEstimator | None = None,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        self._embedder = embedder
        self._client = openrouter_client
        self._pool = db_pool
        self._settings = settings
        self._estimator = estimator or ComplexityEstimator()
        self._log = logger or get_logger(__name__)

        self._agent_names: list[str] = []
        self._agent_matrix: np.ndarray = np.empty((0, 0))
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

        asyncio.create_task(self._write_log(session_id, prompt, envelope))
        return envelope

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_agent_embeddings(self) -> None:
        enabled = self._enabled_agents()
        if not enabled:
            raise RoutingError("No enabled agents found in config")

        self._agent_names = list(enabled.keys())
        descriptions = [cfg["description"].strip() for cfg in enabled.values()]
        self._agent_matrix = self._embedder.encode(descriptions)

    def _enabled_agents(self) -> dict:
        return {
            name: cfg
            for name, cfg in self._settings.agent_configs.items()
            if cfg.get("enabled", True)
        }

    def _resolve_model(self, agent: str, complexity: str) -> str:
        cfg = self._settings.agent_configs.get(agent, {})
        if complexity == "simple" and "model_simple" in cfg:
            return cfg["model_simple"]
        return cfg.get("model", "anthropic/claude-sonnet-4-5")

    def _single_agent_envelope(self, prompt: str) -> RoutingEnvelope:
        agent = self._agent_names[0]
        intent = self._primary_intent(agent)
        complexity = self._estimator.classify(prompt, intent, 1.0)
        model = self._resolve_model(agent, complexity)
        return RoutingEnvelope(
            primary_agent=agent,
            confidence=1.0,
            score_gap=0.0,
            routing_method="embedding",
            is_compound=False,
            subtasks=[SubTask(agent=agent, intent=intent, prompt=prompt, model=model)],
            requires_synthesis=False,
            raw_scores={agent: 1.0},
            complexity=complexity,
        )

    async def _score_and_route(self, prompt: str) -> RoutingEnvelope:
        prompt_vec = self._embedder.encode(prompt)

        # Cosine similarity via dot product (embeddings are unit-normalised)
        scores: list[float] = (self._agent_matrix @ prompt_vec).tolist()
        raw_scores = dict(zip(self._agent_names, scores))

        sorted_pairs = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)
        top_agent, top_score = sorted_pairs[0]
        second_score = sorted_pairs[1][1]
        score_gap = top_score - second_score

        routing_cfg = self._settings.routing_config
        threshold = float(routing_cfg.get("threshold", 0.55))
        gap_threshold = float(routing_cfg.get("gap_threshold", 0.10))

        if top_score < threshold or score_gap < gap_threshold:
            self._log.info(
                "routing_haiku_fallback",
                top_score=round(top_score, 3),
                score_gap=round(score_gap, 3),
                reason="below_threshold" if top_score < threshold else "low_gap",
            )
            set_agent_context("router")
            envelope = await haiku_fallback.decompose(
                prompt=prompt,
                raw_scores=raw_scores,
                client=self._client,
                settings=self._settings,
                logger=self._log,
            )
            primary_intent = envelope.subtasks[0].intent if envelope.subtasks else "read"
            complexity = self._estimator.classify(prompt, primary_intent, envelope.confidence)
            for subtask in envelope.subtasks:
                subtask.model = self._resolve_model(subtask.agent, complexity)
            envelope.complexity = complexity
            return envelope

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

    def _primary_intent(self, agent: str) -> str:
        intent_map = self._settings.agent_configs.get(agent, {}).get("intent_map", {})
        return next(iter(intent_map), "read")

    async def _write_log(
        self, session_id: str, prompt: str, envelope: RoutingEnvelope
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO routing_log
                        (session_id, prompt, method, primary_agent,
                         confidence, score_gap, is_compound, raw_scores,
                         complexity, model_selected)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)
                    """,
                    session_id,
                    prompt,
                    envelope.routing_method,
                    envelope.primary_agent,
                    envelope.confidence,
                    envelope.score_gap,
                    envelope.is_compound,
                    json.dumps(envelope.raw_scores),
                    envelope.complexity,
                    envelope.subtasks[0].model if envelope.subtasks else None,
                )
        except Exception as exc:
            self._log.warning("routing_log_write_failed", error=str(exc))
