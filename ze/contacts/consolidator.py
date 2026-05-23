from __future__ import annotations

import json
import time
from datetime import datetime
from uuid import UUID

import asyncpg

from ze.contacts.store import PersonStore
from ze.contacts.types import ContactsConsolidationReport, Person, PersonSource, SOURCE_WEIGHTS
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.telemetry.context import set_agent_context, set_flow_context

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

_DEFAULTS = {
    "episode_batch_size": 10,
    "max_episodes_per_run": 50,
    "nightly_cron": "0 3 * * *",
}


class ContactsConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        person_store: PersonStore,
        openrouter_client: OpenRouterClient,
        settings: Settings,
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

        cfg = self._cfg()
        batch_size = int(cfg["episode_batch_size"])
        max_episodes = int(cfg["max_episodes_per_run"])

        episodes = await self._load_unprocessed(max_episodes)
        if not episodes:
            self._log.info("contacts_consolidation_no_episodes")
            return ContactsConsolidationReport(duration_ms=int((time.monotonic() - start) * 1000))

        report = ContactsConsolidationReport(episodes_scanned=len(episodes))

        # Process in batches — each batch is one LLM call
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

    async def _extract_candidates(self, batch: list[asyncpg.Record]) -> list[dict]:
        block = _format_batch(batch)
        model = self._settings.config.get("models", {}).get(
            "synthesis", "anthropic/claude-haiku-4-5"
        )
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": block}],
                model=model,
                system=_EXTRACT_SYSTEM,
                max_tokens=800,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                self._log.warning("contacts_extract_bad_shape", raw=raw[:200])
                return []
            return [c for c in parsed if isinstance(c, dict) and "name" in c]
        except Exception as exc:
            self._log.warning("contacts_extract_failed", error=str(exc))
            return []

    async def _store_candidate(self, candidate: dict) -> bool:
        """Upsert a candidate into the person store. Returns True if newly created."""
        name = (candidate.get("name") or "").strip()
        if not name:
            return False

        confidence = float(candidate.get("confidence", 0.5))
        # Clamp to research weight — consolidator never produces conversation-weight contacts
        weight = min(confidence, SOURCE_WEIGHTS["conversation"])
        source_type = "conversation"

        existing = await self._store.get_by_name(name)
        source = PersonSource(
            person_id=UUID(int=0),  # placeholder, replaced below
            source_type=source_type,
            weight=weight,
            raw_context=str(candidate.get("context", ""))[:500],
        )

        if existing:
            # Add this episode's observation as a new source on the best match
            best = existing[0]
            source.person_id = best.id  # type: ignore[assignment]
            await self._store.add_source(best.id, source)  # type: ignore[arg-type]
            return False
        else:
            person = Person(
                name=name,
                classification=_safe_classification(candidate.get("classification")),
                classification_confidence=confidence,
                relationship_to_user=str(candidate.get("relationship", ""))[:500],
                contact_info={
                    k: str(v)
                    for k, v in (candidate.get("contact_info") or {}).items()
                    if v
                },
                notes=str(candidate.get("context", ""))[:500],
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

    def _cfg(self) -> dict:
        cfg = self._settings.contacts_config.get("consolidation", {})
        return {k: cfg.get(k, v) for k, v in _DEFAULTS.items()}


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
