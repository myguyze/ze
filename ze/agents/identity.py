_VERBOSITY_CLAUSES = {
    "concise": " Keep responses brief — one to two paragraphs unless the user asks for more.",
    "detailed": " Be thorough — elaborate fully and include examples where helpful.",
}

_IDENTITY_TEMPLATE = """\
You are Ze, a personal AI assistant. You are {traits}.{verbosity_clause}
{custom_block}
## Known facts about this user
Use these facts to personalise responses and to answer questions about the user directly. \
Do not say you lack information if it appears below.
{memory_context}\
"""


def build_identity_block(persona: dict, memory_context: str) -> str:
    traits = persona.get("traits") or ["helpful"]
    if len(traits) == 1:
        traits_str = traits[0]
    elif len(traits) == 2:
        traits_str = f"{traits[0]} and {traits[1]}"
    else:
        traits_str = ", ".join(traits[:-1]) + f", and {traits[-1]}"

    verbosity = persona.get("verbosity", "balanced")
    verbosity_clause = _VERBOSITY_CLAUSES.get(verbosity, "")

    custom = (persona.get("custom_instructions") or "").strip()
    custom_block = f"\n{custom}" if custom else ""

    return _IDENTITY_TEMPLATE.format(
        traits=traits_str,
        verbosity_clause=verbosity_clause,
        custom_block=custom_block,
        memory_context=memory_context,
    )
