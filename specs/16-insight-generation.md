# Insight Generation — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| Migration 007 — `insights` table | ✅ Done |
| Config `proactive.insights_*` keys | ✅ Done |
| `InsightEngine` — generate and push weekly insights | ✅ Done |
| Container wiring + cron registration | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze has accumulated facts, episodes, and a synthesised user profile. Insight
generation is the step that turns that accumulation into *observations* —
specific, evidence-backed patterns or tensions that the user may not have
consciously noticed. Ze runs a weekly synthesis pass, produces 1–3 short
conversational observations, and pushes them via Telegram.

Examples of what Ze should produce:

- *"I've noticed you've mentioned sleep problems four times this week — anything
  going on?"*
- *"Your last three research sessions all circled back to distributed systems.
  Looks like that's becoming a recurring thread."*
- *"You said you wanted to practise Portuguese more, but I haven't seen that
  come up in our conversations for a couple of weeks."*

---

## Out of Scope

- User replies to insights triggering a follow-up conversation (handled
  naturally by the existing graph when the user responds).
- Inline keyboard buttons on insight messages.
- Per-category suppression controlled by the user (they adjust indirectly by
  conversing with Ze).
- Insight history UI (the `insights` table is queryable via REST if needed later,
  but no dedicated route in this phase).
- Real-time insights after each conversation — weekly cadence only.

---

## Repository Layout

```
ze/
├── proactive/
│   └── insights.py          # InsightEngine
└── migrations/versions/
    └── 007_insights.py
```

Config addition: three new keys under `proactive:` in `config/config.yaml`.

Tests: `tests/proactive/test_insights.py`.

---

## Database Schema

Migration `migrations/versions/007_insights.py`.

```sql
CREATE TABLE insights (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    text         TEXT NOT NULL,
    category     TEXT NOT NULL,   -- pattern | trend | goal | tension
    week_of      DATE NOT NULL,
    pushed       BOOLEAN NOT NULL DEFAULT false,
    pushed_at    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX insights_week_of_idx ON insights (week_of DESC);
CREATE INDEX insights_category_pushed_idx
    ON insights (category, pushed_at DESC)
    WHERE pushed = true;
```

`week_of` is the ISO Monday of the week the insight was generated (`date.today() - timedelta(days=date.today().weekday())`). Used for audit and dedup logic.

---

## Configuration

Add under `proactive:` in `config/config.yaml`:

```yaml
proactive:
  ...                              # existing keys unchanged
  insights_enabled: true
  insights_cron: "0 7 * * 0"      # Sunday 7 AM UTC — before the 8 AM briefing
  insights_model: anthropic/claude-haiku-4-5
  insights_lookback_days: 7        # evidence window
  insights_min_evidence: 3         # min facts OR episodes in window to proceed
  insights_max_per_run: 3          # cap on insights pushed per weekly run
  insights_category_cooldown_days: 7  # suppress same category within this window
```

All keys have code-level defaults. Read via `settings.proactive_config.get(key, default)`.

---

## `InsightEngine` (`ze/proactive/insights.py`)

```python
class InsightEngine:
    def __init__(
        self,
        notifier: ProactiveNotifier,
        pool: asyncpg.Pool,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None: ...

    async def run(self) -> None:
        """Weekly job: generate insights from recent evidence and push any novel ones."""
```

`run()` is the APScheduler job target.

---

## `run()` Logic

### 1. Load evidence

```sql
-- Recent facts (within lookback window)
SELECT key, value, updated_at
FROM user_facts
WHERE contradicted = false
  AND updated_at > NOW() - INTERVAL '{lookback_days} days'
ORDER BY updated_at DESC

-- Recent episodes
SELECT summary, response, created_at
FROM episodes
WHERE created_at > NOW() - INTERVAL '{lookback_days} days'
  AND is_archive = false
ORDER BY created_at DESC

-- User profile
SELECT preferences, habits, topics, relationships, goals
FROM user_profile WHERE id = 1

-- Recent insights (last 4 weeks) for LLM context
SELECT text, category
FROM insights
ORDER BY created_at DESC
LIMIT 20

-- Categories pushed within cooldown window
SELECT DISTINCT category
FROM insights
WHERE pushed = true
  AND pushed_at > NOW() - INTERVAL '{cooldown_days} days'
```

### 2. Minimum evidence check

Count `len(fact_rows) + len(episode_rows)`. If below `insights_min_evidence`,
log and return — do not call the LLM.

### 3. Build prompts

**System:**

```
You are Ze's insight engine. Based on the user's recent activity, identify 1-3
specific observations worth surfacing. Each insight must:
- Reference concrete evidence (specific topics, exact counts, named patterns)
- Be genuinely novel — not already present in the "recent insights" list below
- Be phrased conversationally, as Ze speaking warmly to the user (1-2 sentences)
- End with a gentle open question where natural (not forced)

Return a JSON array of objects with exactly two string keys:
  "text": the observation as Ze would say it
  "category": one of "pattern", "trend", "goal", "tension"

Return [] if there is truly nothing worth surfacing this week.
```

**User:**

```
User profile:
{profile_block or "(no profile yet)"}

Facts from the past {lookback_days} days:
{facts_block}    ← "- key: value" lines, or "(none)"

Recent interaction summaries (past {lookback_days} days):
{episodes_block} ← "- {summary or response[:200]}" lines, or "(none)"

Recent insights already surfaced (avoid repetition):
{recent_insights_block} ← "- [{category}] {text}" lines, or "(none)"

Generate insights.
```

### 4. Call LLM

Model: `insights_model` (default `anthropic/claude-haiku-4-5`). `max_tokens=400`.

On failure (exception or non-JSON response): log warning, return — no crash,
no push.

### 5. Parse and filter

- Parse JSON array. Each item must have `text` (non-empty string) and `category`
  (one of the four valid values). Discard malformed items silently.
- **Category cooldown filter**: discard any item whose `category` appears in
  the `recently_pushed_categories` set from step 1.
- **Cap**: take the first `insights_max_per_run` items from what remains.

### 6. Insert and push

For each surviving insight:

```python
row = await conn.fetchrow(
    "INSERT INTO insights (text, category, week_of) VALUES ($1, $2, $3) RETURNING id",
    insight["text"], insight["category"], week_of,
)
await notifier.push(insight["text"])
await conn.execute(
    "UPDATE insights SET pushed = true, pushed_at = NOW() WHERE id = $1",
    row["id"],
)
```

Insights are inserted and pushed one at a time. If `notifier.push()` swallows an
error, the insight is still marked pushed (Ze tried; Telegram failed; no retry).

Log `insight_pushed` with `category` and a truncated preview of the text.

---

## Delivery Format

Ze pushes each insight as the raw `text` field — no prefix, no label. The LLM
is instructed to phrase the text as Ze speaking, so no wrapper is needed.

Multiple insights in one run are pushed as separate messages, with a 1-second
delay between them (prevents Telegram rate-limiting and feels more natural than
a wall of text).

---

## Container Wiring

In `build_container()`:

```python
insight_engine = InsightEngine(
    notifier=notifier,
    pool=pool,
    openrouter_client=openrouter_client,
    settings=settings,
)
if proactive_cfg.get("insights_enabled", True):
    workflow_scheduler.schedule_job(
        fn=insight_engine.run,
        cron=proactive_cfg.get("insights_cron", "0 7 * * 0"),
        job_id="insight_generation",
    )
    log.info("insights_scheduled")
```

`Container` gains an `insight_engine: InsightEngine` field.

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Below minimum evidence | Log `insights_skipped_sparse`, return — no LLM call |
| Haiku raises | Log warning, return — nothing pushed |
| Haiku returns `[]` | Nothing pushed — Ze found nothing notable |
| Haiku returns malformed JSON | Log warning, return |
| All items filtered by category cooldown | Nothing pushed this week for those categories |
| `text` or `category` missing from an item | Item silently discarded |
| Invalid `category` value | Item discarded |
| `notifier.push()` fails | Error swallowed by notifier — insight still marked pushed |
| No user profile yet | Profile block set to `"(no profile yet)"` — LLM proceeds with facts + episodes only |

---

## Testing

Tests live in `tests/proactive/test_insights.py`.

| Test | What it verifies |
|------|-----------------|
| `test_insights_generates_and_pushes` | Haiku returns valid JSON → insight stored, pushed, marked pushed |
| `test_insights_skips_sparse` | total facts + episodes < min_evidence → no LLM call, no push |
| `test_insights_filters_category_cooldown` | category in recently_pushed_categories → item discarded |
| `test_insights_caps_max_per_run` | Haiku returns 5 items → only max_per_run (3) pushed |
| `test_insights_haiku_failure` | Haiku raises → nothing pushed, no crash |
| `test_insights_bad_json` | Haiku returns non-JSON → nothing pushed |
| `test_insights_empty_array` | Haiku returns `[]` → nothing pushed |
| `test_insights_invalid_category_discarded` | Item has `category: "other"` → discarded |
| `test_insights_passes_recent_to_llm` | Recent insights in DB → their texts appear in LLM prompt |
| `test_insights_no_profile_uses_placeholder` | `user_profile` all-empty → prompt contains placeholder text |

---

## Open Questions

All resolved.
