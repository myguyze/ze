"""Tests for PersonStore.confirm() → entity write path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.contacts.store import PersonStore
from ze_personal.contacts.types import Person
from ze_memory.types import Entity


def _make_person(**kwargs) -> Person:
    defaults = dict(
        id=uuid4(),
        name="Alice Wonderland",
        aliases=[],
        classification="colleague",
        classification_confidence=0.9,
        relationship_to_user="colleague",
        contact_info={"email": "alice@example.com"},
        notes="Met at conference",
        confirmed=True,
        dismissed=False,
        confidence=0.9,
    )
    return Person(**{**defaults, **kwargs})


class _AsyncCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_pool(person: Person) -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={
        "id": person.id,
        "name": person.name,
        "aliases": person.aliases,
        "classification": person.classification,
        "classification_confidence": person.classification_confidence,
        "relationship_to_user": person.relationship_to_user,
        "contact_info": person.contact_info,
        "notes": person.notes,
        "confirmed": True,
        "dismissed": person.dismissed,
        "confidence": person.confidence,
        "first_seen": None,
        "last_mentioned": None,
        "created_at": None,
        "updated_at": None,
    })
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))
    return pool


# ── confirm() → entity write ──────────────────────────────────────────────────

async def test_confirm_writes_entity_when_memory_store_set():
    person = _make_person()
    pool = _make_pool(person)

    memory_store = AsyncMock()
    memory_store.upsert_entity = AsyncMock(return_value=uuid4())

    store = PersonStore(pool=pool, memory_store=memory_store)
    result = await store.confirm(person.id)

    memory_store.upsert_entity.assert_called_once()
    entity: Entity = memory_store.upsert_entity.call_args.args[0]
    assert isinstance(entity, Entity)
    assert entity.entity_type == "person"
    assert entity.canonical_name == person.name


async def test_confirm_entity_includes_relationship_in_attrs():
    person = _make_person(relationship_to_user="mentor")
    pool = _make_pool(person)

    memory_store = AsyncMock()
    memory_store.upsert_entity = AsyncMock(return_value=uuid4())

    store = PersonStore(pool=pool, memory_store=memory_store)
    await store.confirm(person.id)

    entity: Entity = memory_store.upsert_entity.call_args.args[0]
    assert entity.attrs.get("relationship") == "mentor"


async def test_confirm_entity_includes_contact_info_in_attrs():
    person = _make_person(contact_info={"email": "alice@acme.com", "phone": "555-1234"})
    pool = _make_pool(person)

    memory_store = AsyncMock()
    memory_store.upsert_entity = AsyncMock(return_value=uuid4())

    store = PersonStore(pool=pool, memory_store=memory_store)
    await store.confirm(person.id)

    entity: Entity = memory_store.upsert_entity.call_args.args[0]
    assert entity.attrs.get("email") == "alice@acme.com"
    assert entity.attrs.get("phone") == "555-1234"


async def test_confirm_skips_entity_write_when_no_memory_store():
    person = _make_person()
    pool = _make_pool(person)

    store = PersonStore(pool=pool, memory_store=None)
    result = await store.confirm(person.id)

    assert result.name == person.name  # Must still return the confirmed person


async def test_confirm_entity_write_failure_does_not_raise():
    person = _make_person()
    pool = _make_pool(person)

    memory_store = AsyncMock()
    memory_store.upsert_entity = AsyncMock(side_effect=RuntimeError("DB error"))

    store = PersonStore(pool=pool, memory_store=memory_store)
    # Must not raise — entity write failure is swallowed
    result = await store.confirm(person.id)
    assert result.name == person.name
