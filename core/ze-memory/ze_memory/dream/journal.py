"""Dream journal builder — writes a DreamJournalEntry for the morning briefing."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_logging import get_logger

log = get_logger(__name__)

_DEFAULT_JOURNAL_MODEL = "anthropic/claude-haiku-4-5"

_JOURNAL_SYSTEM = (
    "You are Ze, writing your own dream journal. In 2–3 sentences, describe what "
    "you processed and learned overnight. Be concrete: mention what types of patterns "
    "you found, risks surfaced, or insights promoted. Write in first person, past tense. "
    "Keep it under 60 words."
)


class DreamJournal:
    def __init__(self, client: Any, dream_store: Any) -> None:
        self._client = client
        self._dream_store = dream_store

    async def write_entry(
        self,
        run_id: UUID,
        episodes_processed: int,
        insights_promoted: int,
        procedures_extracted: int,
        plan_risks_surfaced: int,
        pending_review: int,
        synthesis_model: str = _DEFAULT_JOURNAL_MODEL,
    ) -> UUID:
        summary = await self._generate_summary(
            episodes_processed=episodes_processed,
            insights_promoted=insights_promoted,
            procedures_extracted=procedures_extracted,
            plan_risks_surfaced=plan_risks_surfaced,
            pending_review=pending_review,
            model=synthesis_model,
        )

        entry_id = await self._dream_store.write_journal_entry(
            run_id=run_id,
            summary=summary,
            episodes_processed=episodes_processed,
            insights_promoted=insights_promoted,
            procedures_extracted=procedures_extracted,
            plan_risks_surfaced=plan_risks_surfaced,
            pending_review=pending_review,
        )

        log.info(
            "dream_journal_written",
            run_id=str(run_id),
            insights_promoted=insights_promoted,
            pending_review=pending_review,
        )
        return entry_id

    async def _generate_summary(
        self,
        episodes_processed: int,
        insights_promoted: int,
        procedures_extracted: int,
        plan_risks_surfaced: int,
        pending_review: int,
        model: str,
    ) -> str:
        if insights_promoted == 0 and pending_review == 0 and plan_risks_surfaced == 0:
            return (
                f"I reviewed {episodes_processed} memory episodes overnight. "
                "No new insights met the promotion threshold."
            )

        prompt = (
            f"Last night I processed {episodes_processed} memory episodes.\n"
            f"Insights promoted to long-term memory: {insights_promoted}\n"
            f"Procedures extracted: {procedures_extracted}\n"
            f"Plan risks surfaced: {plan_risks_surfaced}\n"
            f"Items pending your review: {pending_review}\n"
            "\nWrite a 2–3 sentence dream journal entry."
        )
        try:
            summary = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                system=_JOURNAL_SYSTEM,
                temperature=0.4,
                max_tokens=150,
            )
            return summary.strip()
        except Exception as exc:
            log.warning("journal_summary_failed", error=str(exc))
            return (
                f"I processed {episodes_processed} episodes overnight, "
                f"promoting {insights_promoted} insights "
                f"and surfacing {plan_risks_surfaced} plan risks."
            )
