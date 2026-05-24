# Spec 21 — Telegram Commands: /costs and /memory

## Implementation Status

| Feature | Status |
|---------|--------|
| `/costs` command — monthly spend by agent | ✅ Done |
| `/memory` command — facts + profile snapshot | ✅ Done |
| `costs_summary()` in `ze/telegram/commands.py` | ✅ Done |
| `memory_summary()` in `ze/telegram/commands.py` | ✅ Done |
| Bot routing in `ZeBot._handle_message()` | ✅ Done |

## Problem

Ze has no introspection commands. The user cannot see what Ze has spent or what Ze knows
about them without querying the database directly. Two commands close this gap:

- `/costs` — cost summary from `llm_cost_log`
- `/memory` — user facts + profile snapshot from `user_facts` and `user_profile`

Both are read-only, single-user, and require no new tables or agents.

---

## /costs

### Behaviour

Reports a rolling spend summary for the current calendar month, broken down by agent.
A secondary "today" line gives a quick daily sanity check.

```
💰 *Costs — May 2026*

Today        $0.012
This month   $1.847

By agent (month):
  companion    $0.421
  research     $0.389
  calendar     $0.310
  email        $0.274
  whisper      $0.030
  routing      $0.018
  memory       $0.009
  other        $0.396

Calls: 312  •  Tokens: 1.2M
```

- "other" buckets any agent not in the named list (memory_consolidator, proactive tasks, etc.)
- Dollar values formatted to 3 decimal places; zero-cost rows omitted
- `NULL` `cost_usd` rows (not yet reconciled) are excluded from totals
- Tokens shown as `1.2M` / `842K` / `12K` (SI suffix, one decimal)

### SQL

```sql
SELECT
    agent,
    SUM(cost_usd)          AS cost,
    COUNT(*)               AS calls,
    SUM(total_tokens)      AS tokens
FROM llm_cost_log
WHERE created_at >= date_trunc('month', NOW())
  AND cost_usd IS NOT NULL
GROUP BY agent
ORDER BY cost DESC
```

A second query with `created_at >= CURRENT_DATE` gives the today figure.

---

## /memory

### Behaviour

Two sections: active facts and the profile snapshot.

```
🧠 *What Ze knows about you*

*Facts* (12)
• name: João
• timezone: Europe/Lisbon
• preferred_language: Portuguese
• ...

*Profile*
_Preferences:_ prefers concise replies, no small talk
_Habits:_ morning Telegram check-in
_Topics:_ software engineering, AI, running
_Relationships:_ —
_Goals:_ ship Ze, run a half marathon
```

- Only non-contradicted, non-expired facts are shown (`contradicted = FALSE`)
- Facts sorted by `updated_at DESC`, capped at 20 entries
- If a profile field is empty the label is omitted entirely
- If there are no facts: "No facts recorded yet."
- If there is no profile row: profile section is omitted

---

## Implementation plan

### New: `ze/telegram/commands.py`

A single module with two pure async functions, each taking an asyncpg pool and returning
a formatted string. No LLM calls. No graph invocation.

```python
async def costs_summary(pool) -> str: ...
async def memory_summary(pool) -> str: ...
```

### Changes: `ze/telegram/bot.py`

`handle_message` already checks for `/new` before routing to the graph. Add two more
early-returns in the same block:

```python
if text == "/costs":
    summary = await costs_summary(self._pool)
    await self._bot.send_message(chat_id, summary, parse_mode="Markdown")
    return

if text == "/memory":
    summary = await memory_summary(self._pool)
    await self._bot.send_message(chat_id, summary, parse_mode="Markdown")
    return
```

`ZeBot` gains a `pool` constructor parameter (the asyncpg pool from the container).

### Changes: `ze/container.py`

Pass `pool=pool` when constructing `ZeBot`.

### Tests: `tests/telegram/test_commands.py`

Mock asyncpg pool with `AsyncMock`. Test:
- `costs_summary` with rows → expected formatted string
- `costs_summary` with no rows → "No costs recorded yet."
- `memory_summary` with facts + profile → expected sections
- `memory_summary` with no facts → fallback text
- `memory_summary` with no profile → only facts section shown

---

## Out of scope

- `/help` — not planned
- Date range filters (`/costs --week`) — not planned
- Pagination for facts — 20 is enough for the single-user case
- Exporting data — not planned
