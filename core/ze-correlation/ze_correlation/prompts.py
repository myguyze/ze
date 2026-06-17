CORRELATION_SYSTEM = """\
You are given a focal context (entities of interest) and a neighbourhood of prior memory items \
(facts, past conversations, signals) for ONE user. Decide whether there is a non-obvious connection.

Rules:
- Use ONLY the provided items. Cite each claim by its exact [id].
- If there is no real connection, respond with: {"no_connection": true}
- Express uncertainty plainly. You are offering a hypothesis, not a verdict.
- Prefer disconfirming evidence when present.
- Do not invent connections or cite ids not in the provided list.

Output JSON only (no markdown fences):
{
  "summary": "one-line neutral connection, hedged",
  "narrative": "2-4 sentence reasoning with explicit uncertainty",
  "relation": "pattern" | "causal_guess" | "tension" | "convergence",
  "confidence": 0.0-1.0,
  "evidence_ids": ["<uuid>", ...]
}
Or if no connection found: {"no_connection": true}\
"""


def build_correlation_user_message(
    seed_labels: list[str],
    neighbourhood_blocks: list[str],
) -> str:
    seeds_text = "\n".join(f"- {label}" for label in seed_labels)
    items_text = "\n\n".join(neighbourhood_blocks)
    return (
        f"Focal entities:\n{seeds_text}\n\n"
        f"Neighbourhood ({len(neighbourhood_blocks)} items):\n\n{items_text}"
    )
