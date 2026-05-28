from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ze_core.memory.types import UserProfile

_VERBOSITY_CLAUSES = {
    "concise": " Keep responses brief — one to two paragraphs unless the user asks for more.",
    "detailed": " Be thorough — elaborate fully and include examples where helpful.",
}

_DIAL_CLAUSES: dict[str, list[tuple[float, float, str]]] = {
    "humor": [
        (0.0, 0.2, "Keep responses strictly professional — no humor."),
        (0.8, 1.0, "Wit is central to how you communicate — be openly funny."),
    ],
    "directness": [
        (0.0, 0.2, "Explore topics Socratically — show reasoning, ask questions before concluding."),
        (0.8, 1.0, "State your conclusion first, always. No preamble, no hedging."),
    ],
    "formality": [
        (0.0, 0.2, "Use casual language — first names, contractions, conversational tone."),
        (0.8, 1.0, "Formal and precise throughout — avoid contractions and colloquialisms."),
    ],
    "depth": [
        (0.0, 0.2, "Keep answers at the surface level — one to two sentences unless asked."),
        (0.8, 1.0, "Go deep — full elaboration with edge cases, examples, and alternatives."),
    ],
}

_IDENTITY_TEMPLATE = """\
You are Ze, a personal AI assistant. You are {traits}.{verbosity_clause}{dial_block}
Respond directly to the user's message. Never open with an introduction, a self-description, \
or an offer of help — the user already knows you. Never say "I'm Ze" or "I'm your assistant".

Format responses using Markdown: **bold** for key terms, ## for section headings in longer \
responses, - for bullet lists, and `code` for technical terms or commands. Keep formatting \
purposeful — don't add headers to short conversational replies.
{custom_block}
{profile_block}\
## Known facts about this user
Use these facts to personalise responses and to answer questions about the user directly. \
Do not say you lack information if it appears below.
{memory_context}\
{contacts_block}"""

_PROFILE_LABELS = {
    "preferences": "Preferences",
    "habits": "Habits",
    "topics": "Topics",
    "relationships": "Relationships",
    "goals": "Goals",
}


def _render_dial_clauses(dials: dict[str, float]) -> str:
    clauses = []
    for name, bands in _DIAL_CLAUSES.items():
        value = dials.get(name)
        if value is None:
            continue
        for lo, hi, clause in bands:
            if lo <= value < hi or (hi == 1.0 and value == 1.0):
                clauses.append(clause)
                break
    return (" " + " ".join(clauses)) if clauses else ""


def _render_profile_block(profile: UserProfile) -> str:
    lines = []
    for key, label in _PROFILE_LABELS.items():
        value = getattr(profile, key, "")
        if value:
            lines.append(f"**{label}:** {value}")
    if not lines:
        return ""
    return "## Who this user is\n" + "\n".join(lines) + "\n\n"


def build_identity_block(
    persona: dict,
    memory_context: str,
    profile: UserProfile | None = None,
    contacts_context: str = "",
) -> str:
    traits = persona.get("traits") or ["helpful"]
    if len(traits) == 1:
        traits_str = traits[0]
    elif len(traits) == 2:
        traits_str = f"{traits[0]} and {traits[1]}"
    else:
        traits_str = ", ".join(traits[:-1]) + f", and {traits[-1]}"

    verbosity = persona.get("verbosity", "balanced")
    verbosity_clause = _VERBOSITY_CLAUSES.get(verbosity, "")

    dials = persona.get("dials") or {}
    dial_block = _render_dial_clauses(dials)

    custom = (persona.get("custom_instructions") or "").strip()
    custom_block = f"\n{custom}\n" if custom else ""

    profile_block = _render_profile_block(profile) if profile is not None else ""
    contacts_block = (
        f"\n## People this user knows\n{contacts_context}\n" if contacts_context else ""
    )

    return _IDENTITY_TEMPLATE.format(
        traits=traits_str,
        verbosity_clause=verbosity_clause,
        dial_block=dial_block,
        custom_block=custom_block,
        profile_block=profile_block,
        memory_context=memory_context,
        contacts_block=contacts_block,
    )
