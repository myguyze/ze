from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from ze_personal.contacts.store import PersonStore
from ze_personal.contacts.types import ContactProposal, Person, PersonSource, SOURCE_WEIGHTS
from ze_core.logging import get_logger
from ze_core.telemetry.context import set_agent_context, set_flow_context

_MODEL_DEFAULT = "anthropic/claude-haiku-4-5"
_BATCH_SIZE_DEFAULT = 10
_MAX_EPISODES_DEFAULT = 50

_EXTRACT_SYSTEM = """\
Extract named individuals from AI assistant conversation transcripts.
Return a JSON array of people who are meaningful to the user.

For each person return an object with exactly these keys:
  "name"           — full name or best available (string)
  "classification" — "personal", "professional", or "unknown" (string)
  "relationship"   — how they relate to the user, free text (string)
  "contact_info"   — object with any of: email, phone, company, linkedin — only if explicitly stated
  "confidence"     — 0.1 to 1.0 (number)
  "context"        — one-sentence quote or summary establishing this person (string)

Rules:
- Only include specific named people, not vague references like "a colleague" or "someone"
- Exclude the user themselves
- Exclude well-known public figures unless the user has a direct personal relationship with them
- If the same person appears multiple times, include them once with the best available context
- Return [] if no named individuals are found
"""


@dataclass
class ContactsConsolidationReport:
    episodes_scanned: int = 0
    candidates_extracted: int = 0
    contacts_created: int = 0
    contacts_updated: int = 0
    duration_ms: int = 0


class ContactsConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        person_store: PersonStore,
        openrouter_client: Any,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._store = person_store
        self._client = openrouter_client
        self._settings = settings
        self._log = get_logger(__name__)

    async def run(self) -> ContactsConsolidationReport:
        set_flow_context("contacts_consolidation")
        set_agent_context("contacts_consolidation")
        start = time.monotonic()
        self._log.info("contacts_consolidation_start")

        batch_size, max_episodes = self._batch_config()

        episodes = await self._load_unprocessed(max_episodes)
        if not episodes:
            self._log.info("contacts_consolidation_no_episodes")
            return ContactsConsolidationReport(duration_ms=int((time.monotonic() - start) * 1000))

        report = ContactsConsolidationReport(episodes_scanned=len(episodes))

        for i in range(0, len(episodes), batch_size):
            batch = episodes[i : i + batch_size]
            candidates = await self._extract_candidates(batch)
            report.candidates_extracted += len(candidates)

            for candidate in candidates:
                created = await self._store_candidate(candidate)
                if created:
                    report.contacts_created += 1
                else:
                    report.contacts_updated += 1

            await self._mark_processed([r["id"] for r in batch])

        report.duration_ms = int((time.monotonic() - start) * 1000)
        self._log.info("contacts_consolidation_done", **report.__dict__)
        return report

    # ── Private ───────────────────────────────────────────────────────────────

    async def _load_unprocessed(self, limit: int) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, agent, prompt, response, summary, created_at
                FROM episodes
                WHERE contacts_extracted = false
                  AND is_archive = false
                ORDER BY created_at ASC
                LIMIT $1
                """,
                limit,
            )

    async def _extract_candidates(self, batch: list[asyncpg.Record]) -> list[ContactProposal]:
        block = _format_batch(batch)
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": block}],
                model=self._synthesis_model(),
                system=_EXTRACT_SYSTEM,
                max_tokens=800,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                self._log.warning("contacts_extract_bad_shape", raw=raw[:200])
                return []
            return [
                ContactProposal(
                    name=str(c.get("name", "")).strip(),
                    classification=_safe_classification(c.get("classification")),
                    relationship=str(c.get("relationship", ""))[:500],
                    contact_info={k: str(v) for k, v in (c.get("contact_info") or {}).items() if v},
                    confidence=float(c.get("confidence", 0.5)),
                    confirmed=False,
                    source_type="conversation",
                    raw_context=str(c.get("context", ""))[:500],
                )
                for c in parsed
                if isinstance(c, dict) and c.get("name")
            ]
        except Exception as exc:
            self._log.warning("contacts_extract_failed", error=str(exc))
            return []

    async def _store_candidate(self, candidate: ContactProposal) -> bool:
        """Upsert a candidate into the person store. Returns True if newly created."""
        if not candidate.name:
            return False

        weight = min(candidate.confidence, SOURCE_WEIGHTS["conversation"])

        existing = await self._store.get_by_name(candidate.name)
        source = PersonSource(
            person_id=UUID(int=0),  # placeholder, replaced below
            source_type=candidate.source_type,
            weight=weight,
            raw_context=candidate.raw_context,
        )

        if existing:
            best = existing[0]
            source.person_id = best.id  # type: ignore[assignment]
            await self._store.add_source(best.id, source)  # type: ignore[arg-type]
            return False
        else:
            person = Person(
                name=candidate.name,
                classification=candidate.classification,
                classification_confidence=candidate.confidence,
                relationship_to_user=candidate.relationship,
                contact_info=candidate.contact_info,
                notes=candidate.raw_context,
                confirmed=False,
                dismissed=False,
                confidence=weight,
            )
            stored = await self._store.upsert(person)
            source.person_id = stored.id  # type: ignore[assignment]
            await self._store.add_source(stored.id, source)  # type: ignore[arg-type]
            return True

    async def _mark_processed(self, episode_ids: list[UUID]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE episodes SET contacts_extracted = true WHERE id = ANY($1::uuid[])",
                episode_ids,
            )

    def _batch_config(self) -> tuple[int, int]:
        if self._settings is None:
            return _BATCH_SIZE_DEFAULT, _MAX_EPISODES_DEFAULT
        cfg = getattr(self._settings, "contacts_config", None)
        if cfg is None and isinstance(self._settings, dict):
            cfg = self._settings.get("contacts", {})
        consolidation = (cfg or {}).get("consolidation", {}) if cfg else {}
        batch_size = int(consolidation.get("episode_batch_size", _BATCH_SIZE_DEFAULT))
        max_episodes = int(consolidation.get("max_episodes_per_run", _MAX_EPISODES_DEFAULT))
        return batch_size, max_episodes

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return _MODEL_DEFAULT
        cfg = getattr(self._settings, "config", None)
        if cfg is not None:
            return cfg.get("models", {}).get("synthesis", _MODEL_DEFAULT)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", _MODEL_DEFAULT)
        return _MODEL_DEFAULT


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_batch(batch: list[asyncpg.Record]) -> str:
    parts = []
    for row in batch:
        dt = row["created_at"]
        ts = dt.strftime("%Y-%m-%d %H:%M") if isinstance(dt, datetime) else str(dt)
        text = row["summary"] or row["response"][:400]
        parts.append(f"[{ts}]\nUser: {row['prompt'][:300]}\nZe: {text}")
    return "\n\n---\n\n".join(parts)


def _safe_classification(value: object) -> str:
    if value in ("personal", "professional"):
        return str(value)
    return "unknown"
