from datetime import timezone
from datetime import datetime as dt
from typing import TYPE_CHECKING

from ze.telegram.formatting import bold, code, esc, italic

if TYPE_CHECKING:
    from ze_personal.contacts.store import PersonStore
    from ze_personal.persona.postgres import PostgresPersonaStore as PersonaStore

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
    lines = [f"\U0001f4b0 {bold(f'Costs — {label}')}", ""]
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
        lines.append(f"  {esc(agent):<12} {_fmt_usd(cost)}")
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

    sections: list[str] = [f"\U0001f9e0 {bold('What Ze knows about you')}"]

    if facts:
        sections.append("")
        sections.append(f"{bold('Facts')} ({len(facts)})")
        for row in facts:
            sections.append(f"• {esc(row['key'])}: {esc(row['value'])}")
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
                profile_lines.append(f"{italic(label + ':')} {esc(val)}")
        if profile_lines:
            sections.append("")
            sections.append(bold("Profile"))
            sections.extend(profile_lines)

    return "\n".join(sections)


def _fmt_contact(person) -> str:
    parts = []
    if person.classification and person.classification != "unknown":
        parts.append(esc(person.classification))
    if person.relationship_to_user:
        parts.append(esc(person.relationship_to_user))
    sub = " · ".join(parts) if parts else italic("no relationship noted")
    return f"{bold(person.name)}\n  {sub}"


async def contacts_summary(person_store: "PersonStore") -> str:
    import asyncpg
    async with person_store._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM contacts
            WHERE confirmed = true AND dismissed = false
            ORDER BY last_mentioned DESC NULLS LAST, created_at DESC
            LIMIT 20
            """
        )
    if not rows:
        return "No contacts yet. Ze will add people as you mention them."

    from ze_personal.contacts.store import _person_from_row
    people = [_person_from_row(r) for r in rows]
    lines = [f"\U0001f4c7 {bold('Your contacts')} ({len(people)})"]
    for person in people:
        lines.append("")
        lines.append(_fmt_contact(person))
    lines.append("")
    lines.append(f"{italic('Search: /contacts <name or keyword>')}")
    return "\n".join(lines)


async def contacts_search(person_store: "PersonStore", query: str) -> str:
    people = await person_store.search(query, confirmed_only=False)
    if not people:
        return f"No contacts matching {italic(query)}."

    lines = [f"\U0001f50d {bold(f'Contacts matching \"{query}\"')} ({len(people)})"]
    for person in people:
        lines.append("")
        lines.append(_fmt_contact(person))
        if not person.confirmed:
            lines[-1] += f" {italic('(unconfirmed)')}"
    return "\n".join(lines)


def _dial_bar(value: float, width: int = 10) -> str:
    filled = round(value * width)
    return "▓" * filled + "░" * (width - filled)


async def persona_summary(persona_store: "PersonaStore") -> str:
    state = await persona_store.get_state()
    active = await persona_store.get_active()
    profiles = persona_store.available_profiles()

    dials = active.get("dials") or {}
    dial_names = ["humor", "directness", "formality", "depth"]

    lines = [f"🎭 {bold('Ze persona')} — active: {bold(state.profile)}", ""]
    for name in dial_names:
        value = dials.get(name, 0.5)
        bar = _dial_bar(value)
        override = f" {italic('(override)')}" if name in state.dials else ""
        lines.append(f"{esc(name):<12} {bar}  {value:.1f}{override}")

    if len(profiles) > 1:
        lines.append("")
        lines.append(f"Profiles: {' · '.join(esc(p) for p in profiles)}")

    lines.append("")
    lines.append(italic("Switch:  /persona <profile>"))
    lines.append(italic("Tune:    /persona <dial> <0.0–1.0>"))
    lines.append(italic("Reset:   /persona reset"))

    return "\n".join(lines)


_STATUS_EMOJI = {
    "active":        "🟢",
    "awaiting_gate": "⏸",
    "paused":        "⏸",
    "planning":      "🗂",
    "completed":     "✅",
    "abandoned":     "🚫",
}

_STATUS_ORDER = ["active", "awaiting_gate", "paused", "planning", "completed", "abandoned"]


def _milestone_bar(done: int, total: int, width: int = 8) -> str:
    if total == 0:
        return "░" * width
    filled = round(done / total * width)
    return "▓" * filled + "░" * (width - filled)


async def goals_summary(goal_store) -> str:
    goals = await goal_store.list_all()
    if not goals:
        return "No goals yet. Describe a multi-week objective to get started."

    goals = [g for g in goals if g.status != "abandoned"]
    goals.sort(key=lambda g: _STATUS_ORDER.index(g.status) if g.status in _STATUS_ORDER else 99)

    active_statuses = {"active", "awaiting_gate", "paused", "planning"}
    active_goals = [g for g in goals if g.status in active_statuses]
    done_goals   = [g for g in goals if g.status == "completed"]

    lines = [f"🎯 {bold('Goals')}"]

    if active_goals:
        for goal in active_goals:
            milestones = await goal_store.list_milestones(goal.id)
            total = len(milestones)
            done  = sum(1 for m in milestones if m.status in ("completed", "skipped"))
            pct   = int(done / total * 100) if total else 0
            bar   = _milestone_bar(done, total)

            emoji = _STATUS_EMOJI.get(goal.status, "•")
            lines.append("")
            lines.append(f"{emoji} {bold(esc(goal.title))}")
            lines.append(f"   {bar}  {done}/{total} milestones ({pct}%)")

            if goal.status == "awaiting_gate":
                gate = await goal_store.get_pending_gate(goal.id)
                if gate:
                    lines.append(f"   ⏳ Gate: {italic(esc(gate.title))}")
            elif goal.status in ("active", "planning"):
                pending = [m for m in milestones if m.status == "pending"]
                if pending:
                    lines.append(f"   ↳ Next: {italic(esc(pending[0].title))}")
    else:
        lines.append("")
        lines.append("No active goals.")

    if done_goals:
        lines.append("")
        lines.append(bold(f"Completed ({len(done_goals)})"))
        for goal in done_goals[-5:]:
            lines.append(f"  • {esc(goal.title)}")

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
            return ("error", [f"Invalid dial value {code(args[1])} — must be a number between 0.0 and 1.0."])
        return ("dial", [args[0], args[1]])

    return ("error", [f"Usage: {italic('/persona · /persona <profile> · /persona <dial> <0.0–1.0> · /persona reset')}"])
