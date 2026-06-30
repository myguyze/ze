> ⚠️ **Status: Stale** — Written pre-split (Phases 1–20). References `ze_core/...` paths that no longer exist. See the [package specs below](../README.md#ze-core-specs-core) for current documentation.

---

# Ze Core — Contacts — Spec

## Purpose

Contacts and channel handles are framework-level primitives: who people are and
how to reach them. This spec defines ze-core's ownership of the contact layer and
the clean API for contact extraction.

The channel abstraction (`Channel` ABC, `ChannelRegistry`, `ChannelType`,
`ChannelHandle`) is already in `ze_core/channels/` (Phase 18). This spec adds the
contacts side of that relationship.

---

## Out of Scope

- New contact fields or schema changes.
- Moving `EmailChannel` — Gmail-specific transport; it stays in `ze/`.

---

## Repository Layout

```
packages/
├── ze-core/ze_core/
│   ├── channels/            # Channel ABC, ChannelRegistry, types
│   └── contacts/
│       ├── __init__.py
│       ├── types.py         # Person, PersonSource, PersonRelationship,
│       │                    # PersonCandidate, PersonContext, StaleFollowUpNudge,
│       │                    # ContactProposal, SOURCE_WEIGHTS
│       ├── store.py         # PersonStore
│       ├── channel_store.py # ContactChannelStore
│       └── consolidator.py  # ContactsConsolidator, ContactsConsolidationReport
└── ze/ze/
    └── contacts/
        ├── __init__.py      # empty
        └── extractors.py    # Ze-specific tool-call parsers (email, calendar)
```

---

## Contact Extraction API

There are two distinct mechanisms for populating contacts — they are not redundant:

### 1. Rule-based inline extractors (`ze/contacts/extractors.py`)

Parse structured tool call outputs from Ze's email and calendar agents:

- `extract_email_contacts(tool_calls)` — reads `From:` headers from `get_email` results
- `extract_calendar_contacts(tool_calls)` — reads attendee lists from `list_events` / `create_event` results

These run synchronously after each agent turn, produce `list[ContactProposal]`,
and feed directly into `AgentResult.contact_proposals`. They live in `ze/` because
they filter on Ze-specific tool names (`"get_email"`, `"list_events"`).

### 2. LLM background consolidator (`ze_core/contacts/consolidator.py`)

`ContactsConsolidator` runs nightly. It scans all episodes where
`contacts_extracted = false`, calls an LLM to extract named people from
conversation text, and upserts them into `PersonStore`.

This is the catch-all for agents that don't have structured tool output to parse
(e.g. research agent, companion agent). It lives in ze-core because all its
dependencies are ze-core primitives.

The former `extract_contacts` LLM tool (inline per-turn extraction for the companion
agent) was removed — it was redundant with the consolidator and added an unnecessary
LLM call on every companion turn.

### `ContactProposal` — the shared output type

Both mechanisms produce `ContactProposal` (defined in `ze_core/contacts/types.py`):

```python
@dataclass
class ContactProposal:
    name: str
    classification: str = "unknown"    # "personal" | "professional" | "unknown"
    relationship: str = ""
    contact_info: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5
    confirmed: bool = False
    source_type: str = "conversation"
    raw_context: str = ""
```

`AgentResult.contact_proposals: list[ContactProposal]` carries proposals out of
agents. The `write_memory` orchestration node persists them via `PersonStore` and
writes any email handles to `ContactChannelStore`.

---

## Types (`ze_core/contacts/types.py`)

```python
SOURCE_WEIGHTS: dict[str, float] = {
    "manual":       1.0,
    "conversation": 1.0,
    "email":        0.7,
    "calendar":     0.6,
    "research":     0.2,
}

@dataclass
class Person: ...           # stored contact record
@dataclass
class PersonSource: ...     # provenance entry per contact
@dataclass
class PersonRelationship: ...  # person-to-person link
@dataclass
class PersonCandidate: ...  # intermediate extraction result (not yet persisted)
@dataclass
class PersonContext: ...    # ranked contacts for agent context injection
@dataclass
class StaleFollowUpNudge: ...  # proactive: contact not mentioned recently
@dataclass
class ContactProposal: ...  # typed extraction output (see above)
```

---

## `ContactsConsolidator` (`ze_core/contacts/consolidator.py`)

```python
class ContactsConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        person_store: PersonStore,
        openrouter_client: Any,
        settings: Any = None,   # duck-typed: Settings or dict
    ) -> None: ...

    async def run(self) -> ContactsConsolidationReport: ...
```

Reads `contacts.consolidation` config from `settings` if present:

| Parameter | Default |
|-----------|---------|
| `episode_batch_size` | 10 |
| `max_episodes_per_run` | 50 |
| synthesis model | `anthropic/claude-haiku-4-5` |

---

## Imports in `ze/`

```python
from ze_core.contacts.types import Person, ContactProposal, SOURCE_WEIGHTS
from ze_core.contacts.store import PersonStore
from ze_core.contacts.channel_store import ContactChannelStore
from ze_core.contacts.consolidator import ContactsConsolidator, ContactsConsolidationReport
from ze.contacts.extractors import extract_email_contacts, extract_calendar_contacts
```

---

## Schema Ownership

Contact tables are defined in ze-core's migration chain (`zc005`):

- `contacts` — primary person record
- `contact_sources` — source provenance per person
- `contact_relationships` — person-to-person links
- `contact_channels` — reachable handles per person

Ze's migration adds one Ze-specific column to ze-core's `episodes` table:

```sql
ALTER TABLE episodes
    ADD COLUMN IF NOT EXISTS contacts_extracted BOOLEAN NOT NULL DEFAULT FALSE;
```

This column is only read by `ContactsConsolidator` to track which episodes have
been processed. It belongs in ze's migration because no ze-core code reads it.

---

## Testing

- `tests/contacts/test_store.py` — `PersonStore` CRUD, row mapping
- `tests/contacts/test_channel_store.py` — `ContactChannelStore` CRUD
- `tests/contacts/test_consolidator.py` — consolidator batch processing, LLM mocked
- `tests/contacts/test_extractors.py` — rule-based extractor parsing, no LLM

---

## What This Enables

- ze-core owns the full contact primitive: who people are and how to reach them —
  symmetric with how ze-core owns memory.
- `ContactProposal` is the single typed contract between extraction (any source)
  and persistence (`write_memory` node → `PersonStore`).
- Adding a new Ze agent that surfaces contacts: produce `list[ContactProposal]` in
  `AgentResult`, or write a new extractor in `ze/contacts/extractors.py`. The
  consolidator covers everything else automatically.
