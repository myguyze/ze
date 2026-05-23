import html
from datetime import timezone
from datetime import datetime as dt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ze.persona.store import PersonaStore

_NAMED_AGENTS = {"companion", "research", "calendar", "email", "whisper", "routing", "memory"}


def _fmt_usd(value: float) -> str:
    return f"${value:.3f}"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


async def costs_summary(pool) -> str:
    async with pool.acquire() as conn:
        month_rows = await conn.fetch(
            """
            SELECT agent, SUM(cost_usd) AS cost, COUNT(*) AS calls, SUM(total_tokens) AS tokens
            FROM llm_cost_log
            WHERE created_at >= date_trunc('month', NOW())
              AND cost_usd IS NOT NULL
            GROUP BY agent
            ORDER BY cost DESC
            """
        )
        today_row = await conn.fetchrow(
            """
            SELECT SUM(cost_usd) AS cost
            FROM llm_cost_log
            WHERE created_at >= CURRENT_DATE
              AND cost_usd IS NOT NULL
            """
        )

    if not month_rows:
        return "No costs recorded yet."

    today_cost = float(today_row["cost"] or 0)
    month_total = sum(float(r["cost"]) for r in month_rows)
    total_calls = sum(int(r["calls"]) for r in month_rows)
    total_tokens = sum(int(r["tokens"]) for r in month_rows)

    label = dt.now(tz=timezone.utc).strftime("%B %Y")
    lines = [f"\U0001f4b0 <b>Costs — {html.escape(label)}</b>", ""]
    lines.append(f"Today        {_fmt_usd(today_cost)}")
    lines.append(f"This month   {_fmt_usd(month_total)}")
    lines.append("")
    lines.append("By agent (month):")

    named: dict[str, float] = {}
    other_cost = 0.0
    for row in month_rows:
        agent = row["agent"]
        cost = float(row["cost"])
        if agent in _NAMED_AGENTS:
            named[agent] = named.get(agent, 0.0) + cost
        else:
            other_cost += cost

    for agent, cost in sorted(named.items(), key=lambda x: -x[1]):
        lines.append(f"  {html.escape(agent):<12} {_fmt_usd(cost)}")
    if other_cost > 0:
        lines.append(f"  {'other':<12} {_fmt_usd(other_cost)}")

    lines.append("")
    lines.append(f"Calls: {total_calls}  •  Tokens: {_fmt_tokens(total_tokens)}")
    return "\n".join(lines)


async def memory_summary(pool) -> str:
    async with pool.acquire() as conn:
        facts = await conn.fetch(
            """
            SELECT key, value FROM user_facts
            WHERE contradicted = FALSE
            ORDER BY updated_at DESC
            LIMIT 20
            """
        )
        profile = await conn.fetchrow(
            "SELECT preferences, habits, topics, relationships, goals FROM user_profile LIMIT 1"
        )

    sections: list[str] = ["\U0001f9e0 <b>What Ze knows about you</b>"]

    if facts:
        sections.append("")
        sections.append(f"<b>Facts</b> ({len(facts)})")
        for row in facts:
            sections.append(f"• {html.escape(row['key'])}: {html.escape(row['value'])}")
    else:
        sections.append("")
        sections.append("No facts recorded yet.")

    if profile:
        _PROFILE_LABELS = [
            ("preferences", "Preferences"),
            ("habits",       "Habits"),
            ("topics",       "Topics"),
            ("relationships","Relationships"),
            ("goals",        "Goals"),
        ]
        profile_lines = []
        for field, label in _PROFILE_LABELS:
            val = (profile[field] or "").strip()
            if val:
                profile_lines.append(f"<i>{html.escape(label)}:</i> {html.escape(val)}")
        if profile_lines:
            sections.append("")
            sections.append("<b>Profile</b>")
            sections.extend(profile_lines)

    return "\n".join(sections)


def _dial_bar(value: float, width: int = 10) -> str:
    filled = round(value * width)
    return "▓" * filled + "░" * (width - filled)


async def persona_summary(persona_store: "PersonaStore") -> str:
    state = await persona_store.get_state()
    active = await persona_store.get_active()
    profiles = persona_store.available_profiles()

    dials = active.get("dials") or {}
    dial_names = ["humor", "directness", "formality", "depth"]

    lines = [f"🎭 <b>Ze persona</b> — active: <b>{html.escape(state.profile)}</b>", ""]
    for name in dial_names:
        value = dials.get(name, 0.5)
        bar = _dial_bar(value)
        override = " <i>(override)</i>" if name in state.dials else ""
        lines.append(f"{html.escape(name):<12} {bar}  {value:.1f}{override}")

    if len(profiles) > 1:
        lines.append("")
        lines.append(f"Profiles: {' · '.join(html.escape(p) for p in profiles)}")

    lines.append("")
    lines.append("<i>Switch:  /persona &lt;profile&gt;</i>")
    lines.append("<i>Tune:    /persona &lt;dial&gt; &lt;0.0–1.0&gt;</i>")
    lines.append("<i>Reset:   /persona reset</i>")

    return "\n".join(lines)


def parse_persona_command(text: str) -> tuple[str, list[str]]:
    """Parse '/persona [args...]' → (subcommand, rest).

    Returns one of:
      ("show", [])
      ("profile", [name])
      ("dial", [name, value_str])
      ("reset", [])
      ("error", [message])
    """
    parts = text.strip().split()
    # drop the leading /persona token
    args = parts[1:] if parts and parts[0].startswith("/") else parts

    if not args:
        return ("show", [])

    if args[0] == "reset":
        return ("reset", [])

    if len(args) == 1:
        return ("profile", [args[0]])

    if len(args) == 2:
        try:
            float(args[1])
        except ValueError:
            return ("error", [f"Invalid dial value <code>{html.escape(args[1])}</code> — must be a number between 0.0 and 1.0."])
        return ("dial", [args[0], args[1]])

    return ("error", ["Usage: /persona · /persona &lt;profile&gt; · /persona &lt;dial&gt; &lt;0.0–1.0&gt; · /persona reset"])
