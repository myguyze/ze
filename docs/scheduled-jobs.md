# Ze — Scheduled Jobs & Memory Lifecycle

Ze isn't only reactive. A set of background jobs run on a daily and weekly cadence
to keep memory clean, synthesise a portrait of the user, surface insights, and push
proactive messages — all without the user prompting anything.

This document explains what runs, when, and how each piece feeds into the next.

---

## The memory lifecycle

Every conversation leaves a trace. Over time those traces accumulate into something
richer:

```mermaid
flowchart TD
    A([Conversations]) --> B[User facts + Episodes\nstored per graph run]
    B --> C[Nightly consolidation\n2 AM UTC\ndedup · expire · archive]
    C --> D[User profile synthesis\nend of each consolidation pass]
    D --> E[Weekly insight generation\nSunday 7 AM UTC]
    E --> F([Morning briefing\n8 AM UTC daily])
```

---

## What happens during a conversation

**Facts** (`ze_memory/retriever.py`)

After each `execute_tool` or `draft_response` node, the `write_memory` graph node
fires (fire-and-forget). The `gather_fact_proposals` extractor extracts declarative
facts from the turn and writes them via `store.propose_facts()` with `reviewed = False`.
The native app's `POST /memory/facts/review` endpoint exposes the review/edit/reject
flow.

**Episodes** (`ze_memory/retriever.py`)

A summary of the conversation turn (what was asked, what Ze did, what was decided)
is written automatically as an episode after every run. Episodes don't require user
approval.

**Memory injection**

On the _next_ conversation, `fetch_context` runs a pgvector semantic search over
both facts and episodes, injecting the top-k most relevant results into the agent's
system prompt as `memory_context`. The user profile (see below) is also injected
into every system prompt — not just similar facts, but a synthesised portrait.

---

## Nightly consolidation (2 AM UTC)

**Module:** `ze_memory/consolidator.py`  
**Config:** `memory.consolidation.*` in `config/config.yaml` (optional overrides; defaults in `ze_memory/defaults.py`)

Three tasks run in sequence every night:

### 1. Fact deduplication

Near-duplicate facts dilute retrieval precision and waste token budget. The
consolidator scans all unreviewed facts, computes pairwise cosine similarity, and
merges candidates above the configured thresholds:

| Similarity | Action |
|---|---|
| > 0.95 (`merge_silent_threshold`) | Silent merge — keep the newer fact, mark the older `contradicted = true`. No LLM call. |
| 0.85–0.95 (`merge_llm_threshold`) | LLM merge — Haiku synthesises one value from both, inserts it as a new fact, marks both originals `contradicted = true`. |
| < 0.85 | No action — dissimilar enough to coexist. |

**Reviewed facts are never auto-merged.** A reviewed fact represents an explicit
user decision; touching it automatically would violate that contract.

### 2. Fact expiry

Three rules applied per run:

| Rule | Condition | Action |
|---|---|---|
| Grace delete | `expires_at` is set and has elapsed | Hard-delete |
| Contradicted cleanup | `contradicted = true` and older than `contradicted_ttl_days` (default: 30d) | Hard-delete |
| Stale unreviewed | `reviewed = false` and no activity for `unreviewed_ttl_days` (default: 90d) | Soft-expire: set `expires_at = NOW() + expiry_grace_days` |

Soft-expired facts appear in the morning briefing and in `GET /memory/digest` so the
user can save them before the grace period ends. Reviewed facts are **never** expired
automatically.

### 3. Episode archival

Raw episodes accumulate quickly. Episodes older than `episode_recency_days` (default:
14d) are candidates for archival. When a batch of at least `episode_min_archive_batch`
(default: 10) candidates exists, Haiku summarises them into a single archive row and
the originals are deleted. This keeps the episodes table lean without losing history.

### 4. Profile facet synthesis (end of every consolidation pass)

After dedup + expiry + archival, the consolidator calls `synthesise_profile()`. Haiku
reads all reviewed facts and the most recent episodes (up to `profile.episode_limit`,
default: 50) and produces a structured list of `ProfileFacet` objects upserted into
`memory_profile_facets` by key.

Profile facets are key-value pairs with stability (`stable` | `dynamic`) and confidence
scores. The current facets are available at `GET /memory/profile` and are injected into
every agent's system prompt. Agents see the full synthesised portrait, not individual facts.

Profile synthesis is skipped if fewer than `profile.min_facts` (default: 3) reviewed
facts exist.

---

## Weekly insights (Sunday 7 AM UTC)

**Module:** `ze_personal/jobs/insights.py`  
**Config:** `proactive.insights.*` in `config/config.yaml`

Every Sunday Ze looks back over the past 7 days of facts and episodes and generates
1–3 short, conversational observations — things the user might not have consciously
noticed:

> *"I've noticed you've mentioned sleep problems four times this week — anything going on?"*
>
> *"Your last three research sessions all circled back to distributed systems. Looks like that's becoming a recurring thread."*
>
> *"You said you wanted to practise Portuguese more, but I haven't seen that come up in our conversations for a couple of weeks."*

Insight categories: `pattern` | `trend` | `goal` | `tension`.

The same category won't fire again within `category_cooldown_days` (default: 7d) to
avoid repetition. Insights are pushed via `ProactiveNotifier` (WebSocket or ntfy) before the 8 AM
morning briefing, so they feel like a natural start to the week.

Insight generation is skipped if fewer than `min_evidence` (default: 3) facts +
episodes exist in the lookback window.

---

## Morning briefing (8 AM UTC daily)

**Module:** `ze_personal/jobs/briefing.py`  
**Config:** `proactive.briefing.*` and `news.personalization.*` in `config/config.yaml`

A daily digest pushed via `ProactiveNotifier`. No LLM call — it's a templated summary of stats and headlines:

- **Unreviewed facts** — facts Ze proposed that you haven't confirmed or rejected yet.
  If the count is at or above `unreviewed_nudge_threshold` (default: 5), the briefing
  includes a direct nudge to review them.
- **Upcoming workflows** — scheduled workflow runs in the next 24 hours.
- **Recent failures** — any workflow runs that failed in the past 24 hours.
- **Personalised headlines** — when the `ze-news` plugin is enabled, the briefing appends
  a news section. With enough user facts (≥ `news.personalization.min_facts`, default 5),
  articles are ranked by cosine similarity against a snapshot of the user's interest
  vector built from stored facts and active goal titles. The section is split into two
  clearly labelled buckets:

  ```
  📰 For you (based on your interests):
    • Article title (source)

  🔭 Outside your usual:
    • Article title (source)
  ```

  The discovery bucket (`explore_ratio`, default 20%) is ranked by recency, not by
  interest score, so the user always sees genuinely fresh off-profile content. Below
  the fact threshold, or when personalization is disabled, the section falls back to
  a plain recency-ordered list under `📰 Headlines:`.

The briefing is deduplicated — it will not fire if one was already sent within the past
20 hours.

---

## Calendar sync and reminders (7:45 AM UTC daily)

**Module:** `ze_calendar/jobs/calendar_reminder.py` (`CalendarReminderJob`)  
**Config:** `proactive.calendar.*` in `config/config.yaml`

Each morning `CalendarReminderService` syncs Google Calendar events up to
`sync_days_ahead` (default: 7) days ahead. For each event, Haiku assesses the
appropriate reminder interval (e.g. 15 minutes before a video call vs. 1 hour before
a flight). `WorkflowScheduler` one-shot `DateTrigger` jobs are created accordingly.

When a reminder fires, Ze pushes the event title and time via `ProactiveNotifier`.
A startup replay pass re-registers any reminders that were scheduled before the last
restart and haven't fired yet.

Calendar sync runs at 7:45 AM — before the 8 AM briefing — so upcoming events
with same-day reminders are captured.

---

## Workflow failure alerts (immediate)

**Module:** `ze_personal/workflow/scheduler.py` + `ze_core/proactive/notifier.py`

When a scheduled workflow step fails, Ze pushes an alert immediately — no waiting
for the morning briefing. A `workflow_failure_cooldown_hours` (default: 1h) prevents
alert spam for repeatedly-failing workflows.

---

## Goal advance sweep (every 15 minutes)

**Module:** `ze_personal/goals/executor.py` · registered in `ze_api/container.py`  
**Job id:** `goal_advance_sweep` · **Cron:** `*/15 * * * *`

For each goal with status `ACTIVE`, the sweep calls `GoalExecutor.advance(goal_id)`.
The advance loop either:

- Fires a **verification gate** (push notification with Proceed / Stop / Redirect options),
  setting status to `AWAITING_GATE` until you respond, or
- Runs the next pending **milestone** via the normal agent registry, stores output and
  a learning, and pushes a short progress line (e.g. *"✅ Draft target list done (2/8)"*).

Goals in `AWAITING_GATE`, `PAUSED`, `PLANNING`, `COMPLETED`, or `ABANDONED` are skipped.
The sweep is lightweight — it returns early when there is no actionable next step.

Gate responses are handled conversationally (not on the cron tick): approving
or redirecting calls `advance` again from the conversation handler.

See [docs/goals.md](goals.md) for the full goal engine documentation.

---

## Weekly goal narrative (Sunday 6 PM UTC)

**Module:** `ze_personal/jobs/goal_narrative.py`  
**Cron:** `0 18 * * 0` (configurable via `proactive.goal_narrative.cron`)

For each active goal, Ze synthesises a one-paragraph weekly update: what was completed this week, any pending gate, and what comes next. Pushed via `ProactiveNotifier`. Skips goals that had no activity in the past 7 days.

---

## Weekly goal suggestions (Sunday 7 PM UTC)

**Module:** `ze_personal/jobs/goal_suggestion.py`  
**Cron:** `0 19 * * 0` (configurable via `proactive.goal_suggestion.cron`)

Analyses recent memory facts, episodes, and past goal retrospectives to propose one new multi-week goal. Sent via `ProactiveNotifier` with **Accept** / **Dismiss** options. Accepted suggestions open a goal creation flow. Suppressed if there are already 3+ active goals or if the last suggestion was dismissed within 7 days.

---

## Stuck goal detection (Tuesday 9 AM UTC)

**Module:** `ze_personal/jobs/stuck_goals.py`  
**Cron:** `0 9 * * 2` (configurable via `proactive.stuck_goals.cron`)

Checks all active goals for inactivity:

- **Milestone stuck**: no milestone progress for 48 h on an `ACTIVE` goal.
- **Gate stuck**: a gate in `AWAITING_APPROVAL` for 72 h with no user response.

For each stuck goal, Ze pushes a notification describing the blockage with **Resume** / **Abandon** / **Redirect** options. `last_stuck_alert_at` on the goal prevents duplicate alerts within the same window.

---

## Cost reconciliation (every 15 minutes)

**Module:** `ze_core/telemetry/reconciler.py` (`CostReconciler`) · registered in `ze_api/container.py`  
**Job id:** `cost_reconciliation` · **Cron:** `*/15 * * * *`

Pulls actual billed costs from the OpenRouter API and reconciles them against
estimated records in `llm_cost_log`. Runs frequently to keep cost data fresh.

---

## Stale campaign recovery (every 15 minutes)

**Module:** `ze_prospecting/jobs/campaigns.py` (`recover_stale_campaigns`) · registered via `ProspectingPlugin.register_proactive_jobs()`  
**Job id:** `recover_stale_campaigns` · **Cron:** `*/15 * * * *`

Marks prospecting campaigns that have been running longer than
`PROSPECTING_STALE_TIMEOUT_MINUTES` (default: 10 min) as failed, preventing stuck
campaigns from blocking new runs.

---

## News fetch (every 30 minutes)

**Module:** `ze_news/jobs/fetch.py`  
**Config:** `news.fetch_schedule` in `config/config.yaml`

When the `ze-news` plugin is loaded, a fetch job runs on a configurable cron (default
`*/30 * * * *`). For each enabled source in `news.sources`, it fetches the RSS feed,
embeds each new article title + summary using the shared
`paraphrase-multilingual-MiniLM-L12-v2` model, and upserts into the `news_articles`
table. Duplicate URLs are skipped. Old articles are pruned after `news.retention_days`
(default: 7 days).

Sources are tagged at configuration time (e.g. `global`, `local`, `tech`, `pt`). Tags
are used for filtering by the `get_headlines` tool and the morning briefing.

---

## Full schedule at a glance

| Time (UTC) | Job | Module |
|---|---|---|
| 2:00 AM daily | Memory consolidation + profile synthesis | `ze_memory/consolidator.py` |
| 3:00 AM daily | Contacts consolidation (dedup + merge) | `ze_personal/contacts/consolidator.py` |
| 7:00 AM Sun | Weekly insight generation | `ze_personal/jobs/insights.py` |
| 7:45 AM daily | Calendar sync + reminder scheduling | `ze_calendar/jobs/calendar_reminder.py` |
| 8:00 AM daily | Morning briefing (with personalised headlines) | `ze_personal/jobs/briefing.py` |
| 8:30 AM daily | Contact review suggestions | `ze_personal/jobs/contacts.py` |
| 6:00 PM Sun | Weekly goal narrative | `ze_personal/jobs/goal_narrative.py` |
| 7:00 PM Sun | Weekly goal suggestions | `ze_personal/jobs/goal_suggestion.py` |
| 9:00 AM Tue | Stuck goal detection | `ze_personal/jobs/stuck_goals.py` |
| Every 15 min | Goal advance sweep | `ze_personal/goals/executor.py` |
| Every 15 min | Cost reconciliation | `ze_core/telemetry/reconciler.py` |
| Every 15 min | Stale campaign recovery | `ze_prospecting/jobs/campaigns.py` |
| Every 30 min | News article fetch + embed | `ze_news/jobs/fetch.py` |
| Immediate | Workflow failure alerts | `ze_core/proactive/notifier.py` |
| Immediate | Calendar event reminders (when they fire) | `ze_calendar/jobs/calendar_reminder.py` |
| Immediate | Goal verification gates + milestone progress | `ze_core/proactive/notifier.py` |

All scheduled jobs use APScheduler (via `WorkflowScheduler` or `ProactiveScheduler`)
with Postgres as the job store, so jobs survive process restarts. Cron expressions
are configurable in `config/config.yaml`.

---

## Inspecting memory

| Endpoint | Description |
|---|---|
| `GET /memory/facts` | All stored facts (with review status, expiry) |
| `GET /memory/digest` | Unreviewed facts + upcoming expiries |
| `GET /memory/profile` | Current user profile (latest synthesis) |
| `POST /memory/consolidate` | Trigger a consolidation run manually |
| `POST /memory/facts/review` | Confirm, reject, or edit a proposed fact |

---

## Adjusting the schedule

All cron expressions and thresholds live in `config/config.yaml` under `memory.consolidation`,
`memory.profile`, `memory.insights`, and `proactive`. See
[docs/configuration.md](configuration.md) for the full reference.

To trigger a consolidation manually (e.g. after bulk-approving many facts):

```bash
curl -X POST https://ze-backend.fly.dev/memory/consolidate \
  -H "Authorization: Bearer $ZE_API_KEY"
```
