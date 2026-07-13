"""Signal admission gate — Phase 56.

Every signal passes through this gate before being written to the memory graph.
The gate is cheap (vector/lookup math, no LLM) and runs on every fetched item.

Outcomes:
  admit  — relevance >= tau_admit → write to graph via ingest_signal
  watch  — tau_watch <= relevance < tau_admit → hold in watch buffer;
           if a later related signal raises joint relevance above tau_admit, admit both
  drop   — relevance < tau_watch → discard

The watch buffer lets two individually-marginal signals that share entities
become jointly salient — the mechanism for "two small events that only matter together".

dry_run=True logs decisions without writing to the graph (used for threshold tuning).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from ze_logging import get_logger
from ze_memory.relevance import RelevanceModel, _normalize
from ze_memory.types import Signal

log = get_logger(__name__)

AdmissionOutcome = Literal["admit", "watch", "drop"]


@dataclass
class WatchEntry:
    signal: Signal
    admission_score: float
    normalized_keys: set[str]
    added_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AdmissionGate:
    """Gate that decides whether a signal enters the memory graph.

    Instantiate once per fetch job; the watch buffer is in-process memory.
    """

    def __init__(
        self,
        relevance_model: RelevanceModel,
        memory_store: Any,
        *,
        tau_admit: float = 0.55,
        tau_watch: float = 0.35,
        w_relevance: float = 0.7,
        w_magnitude: float = 0.3,
        watch_buffer_ttl_hours: float = 48,
        dry_run: bool = False,
    ) -> None:
        self._relevance_model = relevance_model
        self._memory_store = memory_store
        self._tau_admit = tau_admit
        self._tau_watch = tau_watch
        self._w_relevance = w_relevance
        self._w_magnitude = w_magnitude
        self._watch_buffer_ttl = timedelta(hours=watch_buffer_ttl_hours)
        self._dry_run = dry_run
        self._watch_buffer: dict[str, WatchEntry] = {}

    async def check_and_ingest(self, signal: Signal) -> AdmissionOutcome:
        rset = await self._relevance_model.build()

        entity_names = [e.name for e in signal.entities]
        topic_names = [e.name for e in signal.entities if e.entity_type == "topic"]
        rel_score = self._relevance_model.score(rset, entity_names, topic_names)

        admission = (
            self._w_relevance * rel_score.value + self._w_magnitude * signal.magnitude
        )

        outcome: AdmissionOutcome
        if admission >= self._tau_admit:
            outcome = "admit"
        elif admission >= self._tau_watch:
            joint = self._joint_admission(signal, admission, entity_names + topic_names)
            if joint >= self._tau_admit:
                outcome = "admit"
            else:
                self._add_to_watch(signal, admission, entity_names + topic_names)
                outcome = "watch"
        else:
            outcome = "drop"

        log.info(
            "signal_admission_decision",
            external_ref=signal.external_ref,
            source=signal.source,
            admission=round(admission, 3),
            relevance=round(rel_score.value, 3),
            magnitude=signal.magnitude,
            outcome=outcome,
            contributions=rel_score.contributions,
            dry_run=self._dry_run,
        )

        if outcome == "admit" and not self._dry_run:
            await self._memory_store.ingest_signal(signal)

        return outcome

    @property
    def watch_buffer_size(self) -> int:
        return len(self._watch_buffer)

    # ── watch buffer ──────────────────────────────────────────────────────────

    def _joint_admission(
        self,
        signal: Signal,
        admission: float,
        keys: list[str],
    ) -> float:
        """Return combined admission if any buffered signal shares keys; else individual.

        Two related watch-range signals that are individually marginal can jointly
        cross tau_admit: joint = min(1.0, a + b).  This is the mechanism that
        lets "two small events that only matter together" get through.
        """
        self._evict_expired()
        nkeys = {_normalize(k) for k in keys}
        for entry in self._watch_buffer.values():
            if nkeys & entry.normalized_keys:
                return min(1.0, admission + entry.admission_score)
        return admission

    def _add_to_watch(
        self,
        signal: Signal,
        admission: float,
        keys: list[str],
    ) -> None:
        self._evict_expired()
        self._watch_buffer[signal.external_ref] = WatchEntry(
            signal=signal,
            admission_score=admission,
            normalized_keys={_normalize(k) for k in keys},
        )

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            k
            for k, v in self._watch_buffer.items()
            if (now - v.added_at) > self._watch_buffer_ttl
        ]
        for k in expired:
            del self._watch_buffer[k]
