from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_personal.contacts.store import PersonStore, _person_from_row, _source_from_row
from ze_personal.contacts.types import Person, PersonRelationship, PersonSource


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_store(pool=None):
    return PersonStore(pool=pool or make_pool())


def make_person_row(**overrides):
    now = datetime.utcnow()
    defaults = {
        "id": uuid4(),
        "name": "João Silva",
        "aliases": [],
        "classification": "professional",
        "classification_confidence": 0.9,
        "relationship_to_user": "charter operator, potential pilot customer",
        "contact_info": {},
        "notes": "",
        "confirmed": True,
        "dismissed": False,
        "confidence": 1.0,
        "first_seen": now,
        "last_mentioned": now,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return defaults


def make_source_row(**overrides):
    defaults = {
        "id": uuid4(),
        "contact_id": uuid4(),
        "source_type": "conversation",
        "weight": 1.0,
        "raw_context": "I met João at the aviation conference",
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return defaults


# ── _person_from_row ──────────────────────────────────────────────────────────

def test_person_from_row_maps_fields():
    row = make_person_row()
    person = _person_from_row(row)

    assert person.id == row["id"]
    assert person.name == "João Silva"
    assert person.classification == "professional"
    assert person.confirmed is True
    assert person.confidence == 1.0
    assert person.relationship_to_user == "charter operator, potential pilot customer"


def test_person_from_row_handles_null_optionals():
    row = make_person_row(relationship_to_user=None, notes=None, contact_info=None, aliases=None)
    person = _person_from_row(row)

    assert person.relationship_to_user == ""
    assert person.notes == ""
    assert person.contact_info == {}
    assert person.aliases == []


# ── _source_from_row ──────────────────────────────────────────────────────────

def test_source_from_row_maps_fields():
    row = make_source_row()
    source = _source_from_row(row)

    assert source.id == row["id"]
    assert source.person_id == row["contact_id"]
    assert source.source_type == "conversation"
    assert source.weight == 1.0


# ── PersonStore.upsert ────────────────────────────────────────────────────────

async def test_upsert_insert_new_person():
    row = make_person_row(id=uuid4(), confirmed=False)
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(make_pool(conn))

    person = Person(name="João Silva", classification="professional", confidence=0.0)
    result = await store.upsert(person)

    assert conn.fetchrow.called
    call_sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO contacts" in call_sql
    assert result.name == "João Silva"


async def test_upsert_updates_existing_person():
    existing_id = uuid4()
    row = make_person_row(id=existing_id)
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(make_pool(conn))

    person = Person(name="João Silva", id=existing_id, confirmed=True, confidence=1.0)
    result = await store.upsert(person)

    call_sql = conn.fetchrow.call_args[0][0]
    assert "UPDATE contacts" in call_sql
    assert result.id == existing_id


# ── PersonStore.get ───────────────────────────────────────────────────────────

async def test_get_returns_person_when_found():
    person_id = uuid4()
    row = make_person_row(id=person_id)
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(make_pool(conn))

    result = await store.get(person_id)

    assert result is not None
    assert result.id == person_id


async def test_get_returns_none_when_not_found():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    store = make_store(make_pool(conn))

    result = await store.get(uuid4())

    assert result is None


# ── PersonStore.confirm ───────────────────────────────────────────────────────

async def test_confirm_sets_confirmed_true():
    person_id = uuid4()
    row = make_person_row(id=person_id, confirmed=True)
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(make_pool(conn))

    result = await store.confirm(person_id)

    assert result.confirmed is True
    call_sql = conn.fetchrow.call_args[0][0]
    assert "confirmed = true" in call_sql


async def test_confirm_raises_when_not_found():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    store = make_store(make_pool(conn))

    try:
        await store.confirm(uuid4())
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ── PersonStore.dismiss ───────────────────────────────────────────────────────

async def test_dismiss_executes_update():
    person_id = uuid4()
    conn = make_conn()
    store = make_store(make_pool(conn))

    await store.dismiss(person_id)

    assert conn.execute.called
    call_sql = conn.execute.call_args[0][0]
    assert "dismissed = true" in call_sql


# ── PersonStore.add_source ────────────────────────────────────────────────────

async def test_add_source_inserts_and_updates_confidence():
    person_id = uuid4()
    conn = make_conn()
    store = make_store(make_pool(conn))

    source = PersonSource(
        person_id=person_id,
        source_type="email",
        weight=0.7,
        raw_context="Ze extracted from email thread",
    )
    await store.add_source(person_id, source)

    assert conn.execute.call_count == 2
    insert_sql = conn.execute.call_args_list[0][0][0]
    update_sql = conn.execute.call_args_list[1][0][0]
    assert "INSERT INTO contact_sources" in insert_sql
    assert "GREATEST(confidence" in update_sql


# ── PersonStore.get_pending ───────────────────────────────────────────────────

async def test_get_pending_returns_empty_when_none():
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[])
    store = make_store(make_pool(conn))

    result = await store.get_pending()

    assert result == []


async def test_get_pending_returns_candidates_with_sources():
    person_id = uuid4()
    person_row = make_person_row(id=person_id, confirmed=False, dismissed=False)
    source_row = make_source_row(contact_id=person_id, source_type="research", weight=0.2)

    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[[person_row], [source_row]])
    store = make_store(make_pool(conn))

    result = await store.get_pending()

    assert len(result) == 1
    person, sources = result[0]
    assert person.id == person_id
    assert len(sources) == 1
    assert sources[0].source_type == "research"


# ── PersonStore.get_context ───────────────────────────────────────────────────

async def test_get_context_returns_empty_when_no_contacts():
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[])
    store = make_store(make_pool(conn))

    ctx = await store.get_context("aviation", token_budget=300)

    assert ctx.people == []
    assert ctx.token_estimate == 0


async def test_get_context_respects_token_budget():
    rows = [
        make_person_row(
            id=uuid4(),
            name="A" * 200,
            relationship_to_user="B" * 200,
            notes="C" * 200,
        )
        for _ in range(5)
    ]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)
    store = make_store(make_pool(conn))

    ctx = await store.get_context("anything", token_budget=50)

    assert len(ctx.people) < 5


# ── PersonStore.add_relationship ─────────────────────────────────────────────

async def test_add_relationship_upserts():
    a_id, b_id = uuid4(), uuid4()
    now = datetime.utcnow()
    row = {
        "id": uuid4(),
        "person_a_id": a_id,
        "person_b_id": b_id,
        "relationship_description": "works at same company",
        "confidence": 0.8,
        "source_type": "conversation",
        "created_at": now,
    }
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(make_pool(conn))

    rel = PersonRelationship(
        person_a_id=a_id,
        person_b_id=b_id,
        relationship_description="works at same company",
        confidence=0.8,
        source_type="conversation",
    )
    result = await store.add_relationship(rel)

    assert result.person_a_id == a_id
    assert result.person_b_id == b_id
    call_sql = conn.fetchrow.call_args[0][0]
    assert "ON CONFLICT" in call_sql
