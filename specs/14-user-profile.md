# User Profile — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| `UserProfile` type + `MemoryContext.profile` field | ✅ Done |
| Migration 005 — user_profile table | ✅ Done |
| `MemoryStore.get_profile()` | ✅ Done |
| `MemoryStore.get_context()` — attach profile | ✅ Done |
| `MemoryConsolidator.synthesise_profile()` | ✅ Done |
| `MemoryConsolidator.run()` — call synthesis, report flag | ✅ Done |
| `identity.py` — profile section in system prompt | ✅ Done |
| REST API — GET /memory/profile | ✅ Done |

---

## Purpose

Individual user facts are precise but shallow — they capture isolated data points.
A user profile synthesises those facts and interaction history into a structured,
human-readable portrait of the user: their preferences, habits, recurring topics,
relationships, and goals. This portrait is injected into every agent's system prompt,
giving Ze durable context about who the user is rather than requiring it to re-infer
personality from isolated facts on every request.

---

## Out of Scope

- User editing of the profile — Ze owns it. Users influence it indirectly by
  confirming, rejecting, and editing facts.
- Per-agent profiles — one profile, injected everywhere.
- Real-time profile updates after each conversation — synthesis runs in the nightly
  consolidation job only.
- Profile history / versioning beyond the current `version` counter.
- Multi-user profiles (single-user system).

---

## Repository Layout

```
ze/
├── memory/
│   ├── types.py          # UserProfile dataclass; MemoryContext.profile field;
│   │                     # ConsolidationReport.profile_updated flag
│   ├── store.py          # get_profile(); get_context() attaches profile
│   └── consolidator.py   # synthesise_profile(); run() calls it last
├── agents/
│   └── identity.py       # _IDENTITY_TEMPLATE gains ## Who this user is block;
│                         # build_identity_block() accepts UserProfile | None
│   └── base.py           # _build_system_prompt() passes memory.profile
├── api/
│   ├── schemas.py        # UserProfileResponse; ConsolidationReportResponse gains
│   │                     # profile_updated
│   └── routes/
│       └── memory.py     # GET /memory/profile
└── migrations/versions/
    └── 005_user_profile.py
```

---

## Data Structures

`ze/memory/types.py` additions and changes:

```python
@dataclass
class UserProfile:
    preferences: str      # communication style, tool preferences, output formats
    habits: str           # routines, recurring activities, work patterns
    topics: str           # domains of interest, recurring subjects
    relationships: str    # people mentioned, their roles relative to the user
    goals: str            # stated objectives, in-progress projects
    updated_at: datetime
    version: int          # incremented on each synthesis run


@dataclass
class MemoryContext:
    facts: list[UserFact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    token_estimate: int = 0
    profile: UserProfile | None = None   # None until first synthesis run


@dataclass
class ConsolidationReport:
    facts_merged: int = 0
    facts_soft_expired: int = 0
    facts_hard_deleted: int = 0
    episodes_archived: int = 0
    episodes_deleted: int = 0
    profile_updated: bool = False        # True if synthesise_profile() wrote a new version
    duration_ms: int = 0
```

Empty string for a `UserProfile` section means "not yet known" — the section is
omitted from the system prompt rather than rendered as a blank heading.

---

## Database Schema

Migration `migrations/versions/005_user_profile.py`.

```sql
CREATE TABLE user_profile (
    id            SERIAL PRIMARY KEY,   -- always row 1; single-user system
    preferences   TEXT NOT NULL DEFAULT '',
    habits        TEXT NOT NULL DEFAULT '',
    topics        TEXT NOT NULL DEFAULT '',
    relationships TEXT NOT NULL DEFAULT '',
    goals         TEXT NOT NULL DEFAULT '',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version       INTEGER NOT NULL DEFAULT 0
);

-- Seed the single row so reads never return NULL.
INSERT INTO user_profile DEFAULT VALUES;
```

The seed `INSERT` runs in `upgrade()` so `get_profile()` can unconditionally
`fetchrow` without handling the empty-table case.

---

## `MemoryStore` changes

### `get_profile()`

```python
async def get_profile(self) -> UserProfile | None:
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT preferences, habits, topics, relationships, goals, updated_at, version "
            "FROM user_profile WHERE id = 1"
        )
    if row is None:
        return None
    # Return None if the profile has never been synthesised (all sections empty).
    if not any([row["preferences"], row["habits"], row["topics"],
                row["relationships"], row["goals"]]):
        return None
    return UserProfile(
        preferences=row["preferences"],
        habits=row["habits"],
        topics=row["topics"],
        relationships=row["relationships"],
        goals=row["goals"],
        updated_at=row["updated_at"],
        version=row["version"],
    )
```

### `get_context()` — attach profile

```python
async def get_context(
    self,
    prompt_embedding: np.ndarray,
    agent: str,
    token_budget: dict[str, int] | None = None,
) -> MemoryContext:
    budget = token_budget or _DEFAULT_BUDGET
    facts = await self._load_facts(agent, budget["facts"], prompt_embedding)
    episodes = await self._load_episodes(prompt_embedding, budget["episodes"])
    profile = await self.get_profile()

    token_estimate = sum(_tokens(f.value) for f in facts)
    token_estimate += sum(_tokens(e.summary or e.response[:200]) for e in episodes)

    return MemoryContext(
        facts=facts,
        episodes=episodes,
        token_estimate=token_estimate,
        profile=profile,
    )
```

`get_profile()` is a single indexed lookup on a one-row table — negligible latency.
No caching needed.

---

## `MemoryConsolidator` changes

### `synthesise_profile()`

```python
async def synthesise_profile(self) -> bool:
    """Synthesise a user profile from reviewed facts and recent episodes.
    Returns True if the profile was updated, False if skipped."""
```

**Skip condition:** fewer than `profile_min_facts` (default: 3) reviewed facts
AND no episodes. Avoids generating a low-quality profile from sparse data.

**Input assembly:**

1. Load all reviewed facts (`reviewed = true`, `contradicted = false`).
2. Load the most recent `profile_episode_limit` (default: 50) episode summaries,
   newest first.
3. Load the current profile (for continuity — Ze updates rather than rewrites
   from scratch).

**Synthesis prompt (system):**

```
You are maintaining a structured profile of a single user based on their
interaction history with a personal AI assistant. Your output must be a JSON
object with exactly five string keys: "preferences", "habits", "topics",
"relationships", "goals". Each value should be a concise paragraph (2–4 sentences)
or an empty string if there is insufficient evidence. Do not invent information.
Base your response only on the provided facts and episode summaries.
```

**Synthesis prompt (user):**

```
Current profile (update rather than replace where possible):
{current_profile_json}

Reviewed user facts:
{facts_block}

Recent interaction summaries (newest first):
{episodes_block}

Produce the updated profile JSON.
```

`current_profile_json` is the existing profile sections as JSON, or `{}` on first run.
`facts_block` is `- key: value` lines. `episodes_block` is `- {summary}` lines.

**On success:** upsert into `user_profile` using `UPDATE … SET … WHERE id = 1`.
Increment `version`, set `updated_at = NOW()`.

**On failure (Haiku error or malformed JSON):** log warning, return `False`. The
existing profile is not touched. The next nightly run will retry.

**Section length cap:** each section is truncated to 400 characters during
synthesis (enforced by a post-parse step, not by the prompt). Keeps total profile
injection under ~500 tokens.

### `run()` — updated

```python
async def run(self) -> ConsolidationReport:
    start = time.monotonic()
    merged = await self.dedup_facts()
    soft_expired, hard_deleted = await self.expire_facts()
    archived, deleted = await self.archive_episodes()
    profile_updated = await self.synthesise_profile()   # runs last
    return ConsolidationReport(
        facts_merged=merged,
        facts_soft_expired=soft_expired,
        facts_hard_deleted=hard_deleted,
        episodes_archived=archived,
        episodes_deleted=deleted,
        profile_updated=profile_updated,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
```

Profile synthesis runs last so it sees the post-dedup, post-expiry state of facts.

---

## System Prompt Injection

### `identity.py`

`build_identity_block()` gains a `profile: UserProfile | None` parameter.

Updated `_IDENTITY_TEMPLATE`:

```
You are Ze, a personal AI assistant. You are {traits}.{verbosity_clause}
{custom_block}
{profile_block}
## Known facts about this user
Use these facts to personalise responses and to answer questions about the user \
directly. Do not say you lack information if it appears below.
{memory_context}
```

`profile_block` is rendered only when `profile` is not `None`. Format:

```
## Who this user is
{preferences_line}
{habits_line}
{topics_line}
{relationships_line}
{goals_line}
```

Where each line is `**Preferences:** {value}` etc., and sections with empty string
values are omitted entirely. A profile where all sections are empty produces no
`profile_block`.

### `base.py`

`_build_system_prompt()` passes the profile through:

```python
def _build_system_prompt(self, agent_instructions, ctx, **extra) -> str:
    identity = build_identity_block(
        self._settings.persona_config,
        self._format_memory(ctx),
        profile=ctx.memory.profile,
    )
    rendered = agent_instructions.format(**extra) if extra else agent_instructions
    return f"{identity}\n\n{rendered}"
```

---

## REST API

### `GET /memory/profile`

Returns the current synthesised profile. Returns `404` if no profile has been
synthesised yet (all sections empty or row not populated).

```python
@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="Current user profile",
    description=(
        "The synthesised user profile — preferences, habits, topics, relationships, "
        "and goals. Updated nightly by the consolidation job."
    ),
)
async def get_profile(pool=Depends(get_pool)) -> UserProfileResponse: ...
```

### Schema addition (`schemas.py`)

```python
class UserProfileResponse(BaseModel):
    preferences: str
    habits: str
    topics: str
    relationships: str
    goals: str
    updated_at: datetime
    version: int


class ConsolidationReportResponse(BaseModel):
    facts_merged: int
    facts_soft_expired: int
    facts_hard_deleted: int
    episodes_archived: int
    episodes_deleted: int
    profile_updated: bool       # new field
    duration_ms: int
```

---

## Configuration

Add under `memory.consolidation` in `config/config.yaml`:

```yaml
memory:
  consolidation:
    ...                          # existing keys unchanged
    profile_min_facts: 3         # skip synthesis below this many reviewed facts
    profile_episode_limit: 50    # max episodes fed into synthesis prompt
    profile_model: anthropic/claude-haiku-4-5  # model for synthesis
```

All three have code-level defaults and are read via `settings.consolidation_config`.

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| No reviewed facts and no episodes | `synthesise_profile()` skips, returns `False` |
| Haiku call fails | Log warning, return `False`, existing profile unchanged |
| Haiku returns malformed JSON | Same — log and return `False` |
| Profile row missing (pre-migration deploy) | `get_profile()` returns `None`; no profile block in prompt |
| All profile sections empty after synthesis | Treat as no profile — return `None` from `get_profile()` |
| Section exceeds 400 chars | Truncated post-parse, before DB write |
| `GET /memory/profile` before first synthesis | 404 |

---

## Testing

Tests live in `tests/memory/test_consolidator.py` (new scenarios) and a new
`tests/api/test_memory_profile.py`.

| Test | What it verifies |
|------|-----------------|
| `test_synthesise_profile_writes_profile` | Haiku returns valid JSON → profile upserted, returns `True` |
| `test_synthesise_profile_skips_sparse` | < min_facts reviewed facts, no episodes → skips, returns `False` |
| `test_synthesise_profile_haiku_failure` | Haiku raises → returns `False`, no DB write |
| `test_synthesise_profile_bad_json` | Haiku returns invalid JSON → returns `False` |
| `test_synthesise_profile_truncates_long_sections` | Section > 400 chars → truncated before write |
| `test_run_includes_profile_updated_flag` | `run()` returns report with `profile_updated=True` |
| `test_get_profile_returns_none_when_empty` | All-empty DB row → `get_profile()` returns `None` |
| `test_get_profile_returns_profile` | Populated DB row → returns `UserProfile` |
| `test_get_context_attaches_profile` | `get_context()` calls `get_profile()` and populates `MemoryContext.profile` |
| `test_identity_block_with_profile` | Non-None profile → "Who this user is" section in rendered string |
| `test_identity_block_without_profile` | `None` profile → no profile section in rendered string |
| `test_identity_block_skips_empty_sections` | Profile with some empty sections → only non-empty rendered |
| `test_api_get_profile_200` | Profile exists → 200 with correct fields |
| `test_api_get_profile_404` | No profile → 404 |

---

## Open Questions

All resolved.
