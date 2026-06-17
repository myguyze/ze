from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import numpy as np

from ze_agents.logging import get_logger

from ze_correlation.engine import CorrelationEngine
from ze_correlation.store import PostgresHypothesisStore
from ze_correlation.types import Hypothesis

log = get_logger(__name__)

UTC = timezone.utc

_PUSH_LOG_KEY = "correlation_push"
_NOVELTY_LOOKBACK_HOURS = 48.0


class CorrelationPushConsumer:
    """Picks recently admitted signals, correlates them, and pushes qualifying hypotheses."""

    def __init__(
        self,
        engine: CorrelationEngine,
        hypothesis_store: PostgresHypothesisStore,
        memory_store: Any,    # PostgresMemoryStore — for seed selection
        notifier: Any,        # ProactiveNotifier
        push_log: Any,        # PushLogStore
        settings: Any,
        embedder: Any = None, # SentenceTransformer — for novelty gate
    ) -> None:
        self._engine = engine
        self._hypothesis_store = hypothesis_store
        self._memory = memory_store
        self._notifier = notifier
        self._push_log = push_log
        self._embedder = embedder
        self._cfg = _load_config(settings)

    async def run_once(self, *, seeds: list[UUID] | None = None) -> list[Hypothesis]:
        """Correlate recent seeds and push qualifying hypotheses.

        Returns all hypotheses formed; a subset (those passing the push bar) are pushed.
        """
        if not self._cfg.enabled and not self._cfg.dry_run:
            log.info("correlation_push_disabled")
            return []

        working_seeds = seeds
        if working_seeds is None:
            working_seeds = await self._pick_seeds()

        if not working_seeds:
            log.info("correlation_push_no_seeds")
            return []

        hypotheses = await self._engine.correlate(working_seeds, mode="proactive")
        if not hypotheses:
            log.info("correlation_push_no_hypotheses", seeds=len(working_seeds))
            return hypotheses

        for hypothesis in hypotheses:
            await self._maybe_push(hypothesis)

        return hypotheses

    # ── private ──────────────────────────────────────────────────────────────

    async def _pick_seeds(self) -> list[UUID]:
        since = datetime.now(UTC) - timedelta(hours=self._cfg.seed_lookback_hours)
        try:
            return await self._memory.list_recent_signal_ids(since, self._cfg.max_seeds_per_run)
        except Exception as exc:
            log.warning("correlation_push_seed_fetch_failed", error=str(exc))
            return []

    async def _maybe_push(self, hypothesis: Hypothesis) -> None:
        if not await self._passes_push_bar(hypothesis):
            log.info(
                "correlation_push_bar_failed",
                hypothesis_id=str(hypothesis.id),
                confidence=hypothesis.confidence,
                relevance=hypothesis.relevance,
            )
            return

        if self._cfg.dry_run:
            log.info(
                "correlation_push_dry_run",
                hypothesis_id=str(hypothesis.id),
                summary=hypothesis.summary,
            )
            return

        await self._notifier.push(
            f"Ze noticed a connection:\n\n{hypothesis.summary}\n\n{hypothesis.narrative}",
            urgency="normal",
        )
        await self._hypothesis_store.mark_surfaced(hypothesis.id)
        await self._push_log.log(_PUSH_LOG_KEY, payload=str(hypothesis.id))
        log.info("correlation_pushed", hypothesis_id=str(hypothesis.id))

    async def _passes_push_bar(self, hypothesis: Hypothesis) -> bool:
        if hypothesis.confidence < self._cfg.tau_push:
            return False
        if hypothesis.relevance < self._cfg.tau_relevance:
            return False
        if not await self._passes_novelty(hypothesis):
            return False
        if not await self._within_budget():
            return False
        return True

    async def _passes_novelty(self, hypothesis: Hypothesis) -> bool:
        if self._embedder is None:
            return True
        try:
            recent_summaries = await self._hypothesis_store.list_recently_surfaced_summaries(
                _NOVELTY_LOOKBACK_HOURS
            )
            if not recent_summaries:
                return True
            new_vec = self._embedder.encode(hypothesis.summary)
            for summary in recent_summaries:
                existing_vec = self._embedder.encode(summary)
                similarity = float(np.dot(new_vec, existing_vec) / (
                    np.linalg.norm(new_vec) * np.linalg.norm(existing_vec) + 1e-9
                ))
                if similarity > self._cfg.novelty_similarity_max:
                    log.info(
                        "correlation_push_novelty_failed",
                        similarity=similarity,
                        threshold=self._cfg.novelty_similarity_max,
                    )
                    return False
        except Exception as exc:
            log.warning("correlation_push_novelty_check_failed", error=str(exc))
        return True

    async def _within_budget(self) -> bool:
        try:
            count = await self._push_log.count_sent_within_hours(_PUSH_LOG_KEY, 24.0)
            return count < self._cfg.max_pushes_per_day
        except Exception as exc:
            log.warning("correlation_push_budget_check_failed", error=str(exc))
            return True


class _PushConfig:
    __slots__ = (
        "enabled", "dry_run", "max_seeds_per_run", "seed_lookback_hours",
        "max_pushes_per_day", "tau_push", "tau_relevance", "novelty_similarity_max",
    )

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _load_config(settings: Any) -> _PushConfig:
    raw = getattr(settings, "config", None)
    if isinstance(raw, dict):
        push_cfg = raw.get("correlation", {}).get("push", {})
        surfacing = raw.get("correlation", {}).get("salience", {}).get("surfacing", {})
        budget = raw.get("correlation", {}).get("salience", {}).get("budget", {})
    elif isinstance(settings, dict):
        push_cfg = settings.get("correlation", {}).get("push", {})
        surfacing = settings.get("correlation", {}).get("salience", {}).get("surfacing", {})
        budget = settings.get("correlation", {}).get("salience", {}).get("budget", {})
    else:
        push_cfg = surfacing = budget = {}

    return _PushConfig(
        enabled=bool(push_cfg.get("enabled", False)),
        dry_run=bool(push_cfg.get("dry_run", True)),
        max_seeds_per_run=int(push_cfg.get("max_seeds_per_run", 20)),
        seed_lookback_hours=float(push_cfg.get("seed_lookback_hours", 8.0)),
        max_pushes_per_day=int(push_cfg.get("max_pushes_per_day", budget.get("max_pushes_per_day", 3))),
        tau_push=float(surfacing.get("tau_push", 0.6)),
        tau_relevance=float(surfacing.get("tau_relevance", 0.5)),
        novelty_similarity_max=float(surfacing.get("novelty_similarity_max", 0.85)),
    )
