# Contacts — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| `contacts` DB table + migrations | ✅ Done |
| `contact_sources` DB table | ✅ Done |
| `contact_relationships` DB table | ✅ Done |
| `Person`, `PersonSource`, `PersonRelationship` types | ✅ Done |
| `PersonStore` — CRUD + search + confirm | ✅ Done |
| `ContactsConsolidator` — nightly episode mining | ✅ Done |
| Agent proposal path — explicit mentions confirmed immediately | ✅ Done |
| Email agent: extract senders/recipients as candidates | ✅ Done |
| Calendar agent: extract attendees as candidates | ✅ Done |
| Confirmation flow via Telegram inline keyboard | ✅ Done |
| `PersonContext` injection into agent prompts | ✅ Done |
| `/contacts` Telegram command | ✅ Done |
| Proactive follow-up reminders | 🔲 Pending |

## Purpose

Track people Ze encounters or is told about. Know who they are, how they relate
to the user, and where Ze first learned about them. Surface low-confidence people
only when relevant and ask the user to confirm before storing them permanently.

## Responsibilities

- Store and retrieve `Person` records with contact info, classification, and free-text relationship description.
- Track the source of every person: conversation mention, email, calendar, research, or manual add.
- Weight sources: conversation and manual carry full confidence; research carries minimal confidence.
- Hold unconfirmed candidates separately; surface them when contextually relevant and ask the user to confirm.
- Track relationships between people (person-to-person graph), separate from the user-to-person relationship.
- Link person records to memory episodes when that person is mentioned.
- Inject relevant person context into agent prompts (similar to `MemoryContext`).

## Out of Scope

- Does not manage Ze's own identity or the user's profile (that is `ze/memory/`).
- Does not send outreach or manage campaigns (that is Phase 12 — Prospecting).
- Does not sync with external CRMs or address books.
- Does not deduplicate names automatically — Ze flags probable duplicates and asks the user.

## Source Weights

| Source | Weight | Behaviour |
|--------|--------|-----------|
| `manual` | 1.0 | User explicitly told Ze about this person. Confirmed immediately. |
| `conversation` | 1.0 | User mentioned the person naturally in chat. Confirmed immediately. |
| `email` | 0.7 | Ze extracted from an email thread. Held as candidate; confirmed when relevant. |
| `calendar` | 0.6 | Ze extracted from a calendar event attendee list. Held as candidate; confirmed when relevant. |
| `research` | 0.2 | Ze found the person during a web search or research task. Held as candidate; confirmed when relevant. |

A person's overall `confidence` is the max weight across all their sources. Confidence increases
as more sources are added. A research-only person at 0.2 never appears in `GET /contacts` or
agent context unless the user confirms them.

## Confirmation Flow

1. Ze encounters a person from a low-weight source (email, calendar, research).
2. Ze creates a `Person` record with `confirmed=False` and stores the source.
3. Ze does not surface this person in general contact queries or agent context.
4. When Ze judges the person is relevant to the current conversation (same domain, user asks
   about them, outreach planning in progress), Ze surfaces a confirmation prompt:

   > "I came across **João Silva** (Commercial Director, TAP Express) while researching
   > regional airlines. Want me to add him to your contacts?"

5. User taps **Yes** → `confirmed=True`, source weight applied.
   User taps **No** → record retained with `dismissed=True` to avoid re-asking.

"When relevant" criteria:
- Current conversation domain matches the person's inferred domain.
- User mentions the same name Ze has seen before (even unconfirmed).
- Ze is building a target list or outreach plan that touches the same segment.
- The person appears in a second independent source (weight accumulates, threshold triggers re-surface).

## Interface Contract

### PersonStore

```python
class PersonStore:
    async def upsert(self, person: Person) -> Person
    async def get(self, person_id: UUID) -> Person | None
    async def get_by_name(self, name: str) -> list[Person]
    async def search(self, query: str, confirmed_only: bool = True) -> list[Person]
    async def get_pending(self) -> list[tuple[Person, list[PersonSource]]]
    async def confirm(self, person_id: UUID) -> Person
    async def dismiss(self, person_id: UUID) -> None
    async def add_source(self, person_id: UUID, source: PersonSource) -> None
    async def add_relationship(self, rel: PersonRelationship) -> PersonRelationship
    async def get_relationships(self, person_id: UUID) -> list[PersonRelationship]
    async def get_context(self, query: str, token_budget: int) -> PersonContext
```

### PersonExtractor

```python
class PersonExtractor:
    async def extract_from_text(
        self,
        text: str,
        source_type: str,
    ) -> list[PersonCandidate]
```

`PersonCandidate` is an intermediate type — a name + context snippet + inferred classification
before the user has confirmed. It is passed to `PersonStore.upsert()` which creates or merges
the `Person` record with `confirmed=False`.

## Data Structures

Lives in `ze/contacts/types.py`.

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

@dataclass
class Person:
    id: UUID
    name: str
    aliases: list[str]                 # nicknames, alternate names
    classification: str                # "personal" | "professional" | "unknown"
    classification_confidence: float   # 0.0–1.0, Ze-inferred from context
    relationship_to_user: str          # free text: "charter operator, potential pilot customer"
    contact_info: dict[str, str]       # {"email": "...", "phone": "...", "linkedin": "..."}
    notes: str                         # accumulated Ze observations
    confirmed: bool                    # False until user confirms
    dismissed: bool                    # True if user said "no" to confirmation
    confidence: float                  # max(source.weight) across all sources
    first_seen: datetime
    last_mentioned: datetime
    created_at: datetime
    updated_at: datetime

@dataclass
class PersonSource:
    id: UUID
    person_id: UUID
    source_type: str                   # "conversation" | "manual" | "email" | "calendar" | "research"
    weight: float                      # from SOURCE_WEIGHTS table
    raw_context: str                   # sentence/email/event that triggered this
    created_at: datetime

@dataclass
class PersonRelationship:
    id: UUID
    person_a_id: UUID
    person_b_id: UUID
    relationship_description: str      # free text: "works at same company as João"
    confidence: float
    source_type: str
    created_at: datetime

@dataclass
class PersonCandidate:
    name: str
    inferred_classification: str
    inferred_relationship: str
    raw_context: str
    source_type: str

@dataclass
class PersonContext:
    people: list[Person]
    token_estimate: int
```

## Database Schema

```sql
CREATE TABLE contacts (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                      TEXT NOT NULL,
    aliases                   TEXT[] DEFAULT '{}',
    classification            TEXT NOT NULL DEFAULT 'unknown',
    classification_confidence FLOAT NOT NULL DEFAULT 0.0,
    relationship_to_user      TEXT,
    contact_info              JSONB DEFAULT '{}',
    notes                     TEXT DEFAULT '',
    confirmed                 BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed                 BOOLEAN NOT NULL DEFAULT FALSE,
    confidence                FLOAT NOT NULL DEFAULT 0.0,
    first_seen                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_mentioned            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX contacts_name_fts_idx ON contacts
    USING gin(to_tsvector('english', name));
CREATE INDEX contacts_confirmed_idx ON contacts(confirmed, dismissed);
CREATE INDEX contacts_classification_idx ON contacts(classification);

CREATE TABLE contact_sources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id   UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    source_type  TEXT NOT NULL,
    weight       FLOAT NOT NULL,
    raw_context  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX contact_sources_contact_id_idx ON contact_sources(contact_id);

CREATE TABLE contact_relationships (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_a_id              UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    person_b_id              UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    relationship_description TEXT NOT NULL,
    confidence               FLOAT NOT NULL DEFAULT 0.5,
    source_type              TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(person_a_id, person_b_id)
);

CREATE INDEX contact_relationships_a_idx ON contact_relationships(person_a_id);
CREATE INDEX contact_relationships_b_idx ON contact_relationships(person_b_id);
```

## Extraction Architecture

Person extraction uses three paths with different triggers and weights. There is no
per-message LLM extraction — conversations accumulate as episodes, and the consolidator
mines them nightly. This keeps real-time cost near zero.

### Path 1 — Agent proposal (explicit, immediate)

When the user clearly introduces a person, the companion agent includes them in
`AgentResult.memory_proposals` as a `UserFact` *and* emits a contact proposal.
This is the only real-time path. It fires only on strong signals:

> "I'm meeting Maria Andrade tomorrow — she's the CCO at Binter Canarias"
> "Remember João Silva, charter operator, CEO of AirLisboa"

Proposed contacts from this path are confirmed immediately (weight 1.0, `confirmed=True`).
Implementation: companion agent system prompt instructs it to emit a structured
`CONTACT:` block in its response when it detects an explicit introduction.

### Path 2 — ContactsConsolidator (nightly batch, scheduled 3 AM UTC)

Mines the `episodes` table for unprocessed conversations. Each episode row has a
`contacts_extracted` flag (added in migration 013); the consolidator processes
only rows where this is `false`.

```
Nightly at 3 AM UTC (after memory consolidation at 2 AM):
  → Load up to 50 unprocessed episodes (contacts_extracted = false)
  → Batch into groups of 10
  → For each batch: LLM extracts named individuals as JSON
  → For each candidate:
      get_by_name() → found → add_source() (update last_mentioned + confidence)
                    → not found → upsert() as unconfirmed + add_source()
  → Mark all processed episodes as contacts_extracted = true
```

Contacts produced this way start unconfirmed. Ze surfaces them when contextually
relevant and asks the user to confirm.

### Path 3 — Email / Calendar agents (triggered at processing time)

When Ze processes email or calendar data it is already reading that content, so
person extraction adds no extra LLM call — just header parsing:

- **Email agent**: extract `From:`, `To:`, `Cc:` → `source_type="email"`, `weight=0.7`
- **Calendar agent**: extract attendees → `source_type="calendar"`, `weight=0.6`

Both create unconfirmed candidates. Ze surfaces them when the person appears
in conversation or when the user asks about contacts.

### Agent context injection

Before agent execution, `PersonContext` is fetched from `PersonStore.get_context(query)`
and injected into the agent system prompt alongside `MemoryContext`. Only confirmed
contacts are included. Budget: ~300 tokens.

## Telegram Commands

| Command / Intent | Behaviour |
|-----------------|-----------|
| "Remember [name], [description]" | Creates confirmed person immediately |
| "What do you know about [name]?" | Returns person record + linked episodes |
| "Show my contacts" | Lists confirmed contacts, grouped by classification |
| "Who have I not spoken to recently?" | Surfaces confirmed contacts by `last_mentioned` ascending |
| `/contacts` | Same as "show my contacts" |
| Confirmation prompt → Yes | `PersonStore.confirm(person_id)` |
| Confirmation prompt → No | `PersonStore.dismiss(person_id)` |

## Proactive Follow-ups

If a confirmed contact has `last_mentioned` older than a threshold (configurable in
`config.yaml`, default 21 days for professional, 14 days for personal), Ze surfaces a
reminder during the morning briefing:

> "You haven't mentioned **Maria Andrade** in 3 weeks — you noted she was interested in
> following up after the AeroLedger demo."

Threshold config lives under `proactive.contacts` in `config/config.yaml`.

## Duplicate Detection

Ze does not silently merge. When `PersonExtractor` returns a name that fuzzy-matches an
existing contact (Levenshtein distance < 3, or embedding similarity > 0.9 on name + context),
Ze flags it and asks:

> "Is **João Silva (AirLisboa)** the same person as **João Silva** you mentioned last week?"

User confirms → merge. User says no → both records kept.

## Module Layout

```
ze/contacts/
├── __init__.py
├── types.py          # Person, PersonSource, PersonRelationship, PersonCandidate, PersonContext
├── store.py          # PersonStore
└── extractor.py      # PersonExtractor — LLM-based extraction from text
```

`PersonStore` is wired in `ze/container.py` and injected into `AgentContext` alongside
`MemoryStore`. `PersonExtractor` is instantiated inside the `extract_people` task.
