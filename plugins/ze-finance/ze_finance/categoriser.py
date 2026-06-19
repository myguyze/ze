from __future__ import annotations

import json

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger

log = get_logger(__name__)

_ANTHROPIC_MODEL = "anthropic/claude-haiku-4-5"

_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("Food & Dining",   ["uber eats", "deliveroo", "bolt food", "glovo", "continente",
                         "pingo doce", "lidl", "aldi", "mercadona", "mcdonald",
                         "starbucks", "nando", "pizza"]),
    ("Transport",       ["uber", "bolt", "cp comboios", "metro", "carris", "ryanair",
                         "tap air", "easyjet", "renfe", "shell", "bp ", "galp"]),
    ("Utilities",       ["edp ", "galp energia", "nos ", "meo ", "vodafone", "epal",
                         "internet", "electricity", "gas "]),
    ("Health",          ["farmacia", "pharmacy", "clinica", "hospital", "dr ", "dra "]),
    ("Entertainment",   ["netflix", "spotify", "steam", "playstation", "xbox",
                         "youtube", "prime video", "hbo", "disney"]),
    ("Shopping",        ["amazon", "zara", "h&m", "fnac", "worten", "leroy merlin"]),
    ("Finance",         ["transferwise", "wise", "revolut", "trading 212", "degiro",
                         "fee", "commission", "interest"]),
]

_BATCH_PROMPT = """\
Classify each transaction description into one of these categories:
Food & Dining, Transport, Utilities, Health, Entertainment, Shopping, Finance, Other.

Descriptions:
{descriptions}

Return ONLY a JSON array of category strings, same length as the input list.
Example: ["Food & Dining", "Transport", "Other"]
"""


class CategoryInferrer:
    """Assigns a spending category to each transaction.

    Keyword rules run first (free, no data exposure).
    If llm_enabled=True, descriptions that fall through to "Other" are batched
    and sent to Anthropic haiku. Only description strings are sent — no amounts,
    dates, or account identifiers.
    """

    def __init__(self, client: LLMClient | None, llm_enabled: bool) -> None:
        self._client = client
        self._llm_enabled = llm_enabled and client is not None

    def infer_keyword(self, description: str) -> str:
        lowered = description.lower()
        for category, keywords in _KEYWORD_RULES:
            if any(kw in lowered for kw in keywords):
                return category
        return "Other"

    async def infer_batch(self, descriptions: list[str]) -> list[str]:
        results = [self.infer_keyword(d) for d in descriptions]
        if not self._llm_enabled:
            return results

        unresolved_indices = [i for i, c in enumerate(results) if c == "Other"]
        if not unresolved_indices:
            return results

        batch = [descriptions[i] for i in unresolved_indices]
        try:
            llm_categories = await self._call_llm(batch)
            for idx, category in zip(unresolved_indices, llm_categories):
                results[idx] = category
        except Exception as exc:
            log.warning("category_llm_failed", error=str(exc), batch_size=len(batch))

        return results

    async def _call_llm(self, descriptions: list[str]) -> list[str]:
        desc_text = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
        prompt = _BATCH_PROMPT.format(descriptions=desc_text)
        response = await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=_ANTHROPIC_MODEL,
        )
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        categories: list[str] = json.loads(text)
        if len(categories) != len(descriptions):
            log.warning("category_llm_length_mismatch", expected=len(descriptions), got=len(categories))
            categories = (categories + ["Other"] * len(descriptions))[: len(descriptions)]
        return categories
