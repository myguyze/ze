"""Profile synthesis: derive ProfileFacets from facts and episode summaries."""

from __future__ import annotations

import json
from typing import Any

from ze_logging import get_logger

from ze_memory.defaults import MODEL_SYNTHESIS

log = get_logger(__name__)

_STABILITY_LEVELS = ("stable", "dynamic", "transient")


class ProfileSynthesizer:
    def __init__(
        self,
        store: Any,
        openrouter_client: Any,
        settings: Any = None,
    ) -> None:
        self._store = store
        self._client = openrouter_client
        self._settings = settings

    async def update_profile(self) -> bool:
        facts_rows = await self._store.fetch_active_fact_summaries(limit=100)
        episode_rows = await self._store.fetch_recent_episode_summaries(limit=20)

        if not facts_rows and not episode_rows:
            return False

        facts_text = "\n".join(f"- {r['predicate']}: {r['value']}" for r in facts_rows)
        episodes_text = "\n".join(f"- {r['summary']}" for r in episode_rows)

        prompt = (
            "Based on these user facts and recent conversation summaries,"
            " synthesize a structured user profile as a JSON array of facets.\n"
            'Each facet: {"key": "snake_case", "value": "...",'
            ' "stability": "stable|dynamic|transient", "confidence": 0.0-1.0}\n'
            "Only include facets derivable from the provided data. Return the JSON array only.\n\n"
            f"Facts:\n{facts_text}\n\nRecent conversations:\n{episodes_text}"
        )

        try:
            response = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._synthesis_model(),
            )
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            facets_data = json.loads(text.strip())
            if not isinstance(facets_data, list):
                raise ValueError("expected a JSON array")
        except Exception as exc:
            log.warning("memory_update_profile_failed", error=str(exc))
            return False

        valid = [
            f
            for f in facets_data
            if isinstance(f, dict)
            and f.get("key")
            and f.get("value")
            and f.get("stability") in _STABILITY_LEVELS
        ]
        if not valid:
            return False

        await self._store.upsert_profile_facets(valid)
        return True

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
