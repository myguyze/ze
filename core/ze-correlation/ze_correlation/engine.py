from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from ze_logging import get_logger

from ze_correlation.prompts import CORRELATION_SYSTEM, build_correlation_user_message
from ze_correlation.store import PostgresHypothesisStore
from ze_correlation.types import EvidenceRef, Hypothesis

log = get_logger(__name__)

UTC = timezone.utc

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
_PIN_DURATION_DAYS = 90
_TAU_REL_PROACTIVE = 0.5


@dataclass
class _CorrelationConfig:
    max_hops_inline: int = 1
    max_hops_proactive: int = 2
    neighbourhood_limit_inline: int = 15
    neighbourhood_limit_proactive: int = 30
    max_seeds_inline: int = 5
    timeout_seconds_inline: float = 5.0
    model: str = _DEFAULT_MODEL


# Internal representation of a materialized neighbourhood item.
@dataclass
class _Item:
    kind: str
    id: str          # UUID as string — matches what the LLM will cite
    label: str
    text: str        # rendered block for the prompt
    external_ref: str | None
    ingested_at: datetime | None


class CorrelationEngine:
    def __init__(
        self,
        memory_store: Any,       # PostgresMemoryStore — graph expand + retrieval
        relevance_model: Any,    # Phase 56 RelevanceModel
        llm_client: Any,         # ze_agents LLMClient protocol
        hypothesis_store: PostgresHypothesisStore,
        settings: Any,
    ) -> None:
        self._memory = memory_store
        self._relevance = relevance_model
        self._llm = llm_client
        self._store = hypothesis_store
        self._cfg = _load_config(settings)

    async def correlate(
        self,
        seeds: list[UUID],
        *,
        mode: Literal["inline", "proactive"],
    ) -> list[Hypothesis]:
        """Expand neighbourhood, run graph-only correlation, persist. Returns formed hypotheses."""
        if not seeds:
            return []

        graph_store = getattr(self._memory, "graph_store", None)
        if graph_store is None:
            log.info("correlation_skipped_no_graph")
            return []

        # 1. Limit seeds for inline mode
        working_seeds = list(seeds)
        if mode == "inline" and len(working_seeds) > self._cfg.max_seeds_inline:
            working_seeds = await self._top_seeds(working_seeds, self._cfg.max_seeds_inline)

        # 2. Expand neighbourhood
        max_hops = self._cfg.max_hops_inline if mode == "inline" else self._cfg.max_hops_proactive
        limit = (
            self._cfg.neighbourhood_limit_inline
            if mode == "inline"
            else self._cfg.neighbourhood_limit_proactive
        )
        expansion = await graph_store.expand(working_seeds, max_hops=max_hops, limit=limit)
        if expansion.is_empty():
            log.info("correlation_empty_neighbourhood", seeds=len(working_seeds), mode=mode)
            return []

        # 3. Relevance prefilter (proactive only; inline skips — user asked)
        if mode == "proactive":
            rset = await self._relevance.build()
            entity_names = await self._entity_names(working_seeds)
            score = self._relevance.score(rset, entity_names, topics=[])
            if score.value < _TAU_REL_PROACTIVE:
                log.info("correlation_prefilter_dropped", relevance=score.value)
                return []
            cached_relevance: float = score.value
        else:
            cached_relevance = 0.0  # computed after LLM call for inline

        # 4. Materialize neighbourhood rows
        neighbourhood = await self._materialize(expansion, set(str(s) for s in working_seeds))
        if not neighbourhood:
            log.info("correlation_empty_materialised", mode=mode)
            return []

        # 5. LLM correlation call (with timeout for inline)
        seed_labels = await self._entity_names(working_seeds)
        coro = self._correlation_call(seed_labels, neighbourhood)
        if mode == "inline":
            try:
                llm_out = await asyncio.wait_for(coro, timeout=self._cfg.timeout_seconds_inline)
            except asyncio.TimeoutError:
                log.info("correlation_inline_timeout", seeds=len(working_seeds))
                return []
        else:
            llm_out = await coro

        if llm_out is None:
            return []

        # 6. Validate: all cited ids must be in the neighbourhood
        known_ids = {item.id for item in neighbourhood}
        cited_ids: list[str] = llm_out.get("evidence_ids", [])
        invalid = set(cited_ids) - known_ids
        if invalid:
            log.warning("correlation_hallucinated_ids", count=len(invalid))
            return []

        # 7. Build evidence refs — all graph_recall (graph-only step)
        now = datetime.now(UTC)
        id_to_item = {item.id: item for item in neighbourhood}
        evidence = [
            EvidenceRef(
                kind=id_to_item[eid].kind,  # type: ignore[arg-type]
                id=UUID(eid),
                label=id_to_item[eid].label,
                external_ref=id_to_item[eid].external_ref,
                origin="graph_recall",
                retrieved_at=now,
                ingested_at=id_to_item[eid].ingested_at,
            )
            for eid in cited_ids
            if eid in id_to_item
        ]

        # 8. Recall guarantee: ≥2 distinct graph_recall items from distinct prior signals/events
        if len(evidence) < 2:
            log.info("correlation_recall_guarantee_failed", evidence_count=len(evidence))
            return []

        # 9. Compute relevance for inline (proactive already has it)
        if mode == "inline":
            try:
                rset = await self._relevance.build()
                entity_names = await self._entity_names(working_seeds)
                score = self._relevance.score(rset, entity_names, topics=[])
                cached_relevance = score.value
            except Exception as exc:
                log.warning("correlation_relevance_score_failed", error=str(exc))
                cached_relevance = 0.0

        # 10. Form hypothesis
        hypothesis = Hypothesis(
            id=uuid4(),
            summary=llm_out["summary"],
            narrative=llm_out["narrative"],
            relation=llm_out["relation"],
            confidence=float(llm_out["confidence"]),
            relevance=cached_relevance,
            evidence=evidence,
            entities=working_seeds,
            created_at=now,
            surfaced=False,
        )

        # 11. Pin cited signals so evidence is never pruned while hypothesis is live
        signal_ids = [e.id for e in evidence if e.kind == "signal"]
        if signal_ids:
            pin_until = now + timedelta(days=_PIN_DURATION_DAYS)
            try:
                await self._memory.pin_signals(signal_ids, pin_until)
            except Exception as exc:
                log.warning("correlation_pin_signals_failed", error=str(exc))

        # 12. Persist
        await self._store.save(hypothesis)
        log.info(
            "hypothesis_formed",
            hypothesis_id=str(hypothesis.id),
            confidence=hypothesis.confidence,
            relation=hypothesis.relation,
            mode=mode,
        )
        return [hypothesis]

    # ── private helpers ───────────────────────────────────────────────────────

    async def _top_seeds(self, seeds: list[UUID], n: int) -> list[UUID]:
        """Return the top-N seeds ranked by relevance score."""
        try:
            rset = await self._relevance.build()
            scored: list[tuple[float, UUID]] = []
            for seed in seeds:
                names = await self._entity_names([seed])
                s = self._relevance.score(rset, names, topics=[])
                scored.append((s.value, seed))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [seed for _, seed in scored[:n]]
        except Exception as exc:
            log.warning("correlation_top_seeds_failed", error=str(exc))
            return seeds[:n]

    async def _entity_names(self, entity_ids: list[UUID]) -> list[str]:
        """Fetch canonical names for a list of entity UUIDs."""
        if not entity_ids:
            return []
        try:
            entities = await self._memory.get_entities_by_ids(entity_ids)
            return [e.canonical_name for e in entities]
        except Exception as exc:
            log.warning("correlation_entity_names_failed", error=str(exc))
            return []

    async def _materialize(
        self,
        expansion: Any,
        seed_ids_str: set[str],
    ) -> list[_Item]:
        """Fetch actual rows for the graph expansion and render them as prompt items."""
        items: list[_Item] = []

        if expansion.fact_ids:
            try:
                facts = await self._memory.get_facts_by_ids(list(expansion.fact_ids))
                for f in facts:
                    if f.id is None or str(f.id) in seed_ids_str:
                        continue
                    items.append(_Item(
                        kind="fact",
                        id=str(f.id),
                        label=f"{f.predicate}: {f.value[:60]}",
                        text=(
                            f"[fact:{f.id}]\n"
                            f"Predicate: {f.predicate}\n"
                            f"Value: {f.value}\n"
                            f"Confidence: {f.confidence:.2f}"
                        ),
                        external_ref=None,
                        ingested_at=None,
                    ))
            except Exception as exc:
                log.warning("correlation_materialize_facts_failed", error=str(exc))

        if expansion.episode_ids:
            try:
                episodes = await self._memory.get_episodes_by_ids(list(expansion.episode_ids))
                for ep in episodes:
                    if ep.id is None or str(ep.id) in seed_ids_str:
                        continue
                    date_str = ep.created_at.strftime("%b %d") if ep.created_at else "?"
                    items.append(_Item(
                        kind="episode",
                        id=str(ep.id),
                        label=f"[{date_str}] {ep.prompt[:60]}",
                        text=(
                            f"[episode:{ep.id}]\n"
                            f"Date: {ep.created_at}\n"
                            f"User: {ep.prompt[:300]}\n"
                            f"Assistant: {ep.response[:300]}"
                        ),
                        external_ref=None,
                        ingested_at=ep.created_at,
                    ))
            except Exception as exc:
                log.warning("correlation_materialize_episodes_failed", error=str(exc))

        if expansion.signal_ids:
            try:
                signals = await self._memory.get_signals_by_ids(list(expansion.signal_ids))
                for sig, ingested_at in signals:
                    if str(sig.id) in seed_ids_str:
                        continue
                    date_str = sig.occurred_at.strftime("%b %d") if sig.occurred_at else "?"
                    items.append(_Item(
                        kind="signal",
                        id=str(sig.id),
                        label=f"{sig.title} ({date_str})",
                        text=(
                            f"[signal:{sig.id}]\n"
                            f"Source: {sig.source}\n"
                            f"Occurred: {sig.occurred_at}\n"
                            f"Title: {sig.title}\n"
                            f"Summary: {sig.summary}"
                        ),
                        external_ref=sig.external_ref,
                        ingested_at=ingested_at,
                    ))
            except Exception as exc:
                log.warning("correlation_materialize_signals_failed", error=str(exc))

        return items

    async def _correlation_call(
        self,
        seed_labels: list[str],
        neighbourhood: list[_Item],
    ) -> dict | None:
        blocks = [item.text for item in neighbourhood]
        user_msg = build_correlation_user_message(seed_labels, blocks)
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": user_msg}],
                model=self._cfg.model,
                system=CORRELATION_SYSTEM,
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            log.warning("correlation_llm_failed", error=str(exc))
            return None

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("correlation_llm_json_parse_failed", error=str(exc))
            return None

        if parsed.get("no_connection"):
            log.info("correlation_no_connection_reported")
            return None

        required = {"summary", "narrative", "relation", "confidence", "evidence_ids"}
        if not required.issubset(parsed):
            log.warning("correlation_llm_missing_fields", keys=list(parsed.keys()))
            return None

        valid_relations = {"pattern", "causal_guess", "tension", "convergence"}
        if parsed.get("relation") not in valid_relations:
            log.warning("correlation_invalid_relation", relation=parsed.get("relation"))
            return None

        confidence = parsed.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            log.warning("correlation_invalid_confidence", confidence=confidence)
            return None

        return parsed


def _load_config(settings: Any) -> _CorrelationConfig:
    cfg: dict = {}
    raw = getattr(settings, "config", None)
    if isinstance(raw, dict):
        cfg = raw.get("correlation", {}).get("engine", {})
    elif isinstance(settings, dict):
        cfg = settings.get("correlation", {}).get("engine", {})
    return _CorrelationConfig(
        max_hops_inline=int(cfg.get("max_hops_inline", 1)),
        max_hops_proactive=int(cfg.get("max_hops_proactive", 2)),
        neighbourhood_limit_inline=int(cfg.get("neighbourhood_limit_inline", 15)),
        neighbourhood_limit_proactive=int(cfg.get("neighbourhood_limit_proactive", 30)),
        max_seeds_inline=int(cfg.get("max_seeds_inline", 5)),
        timeout_seconds_inline=float(cfg.get("timeout_seconds_inline", 5.0)),
        model=str(cfg.get("model", _DEFAULT_MODEL)),
    )
