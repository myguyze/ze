import pathlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ze.contacts.consolidator import ContactsConsolidator, _format_batch, _safe_classification
from ze.contacts.types import Person
from ze.settings import Settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    from ze.settings import get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


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


def make_episode_row(**overrides):
    defaults = {
        "id": uuid4(),
        "agent": "companion",
        "prompt": "I had a call with João Silva from AirLisboa today.",
        "response": "That's great progress on H1.",
        "summary": "User called João Silva at AirLisboa. Validated H1.",
        "created_at": datetime(2026, 5, 23, 14, 30),
    }
    defaults.update(overrides)
    return defaults


def make_person_store(get_by_name_result=None, upsert_result=None):
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=get_by_name_result or [])
    default_person = Person(
        name="João Silva",
        id=uuid4(),
        confirmed=False,
        confidence=0.8,
    )
    store.upsert = AsyncMock(return_value=upsert_result or default_person)
    store.add_source = AsyncMock()
    return store


def make_consolidator(pool=None, person_store=None, client=None, settings=None):
    return ContactsConsolidator(
        pool=pool or make_pool(),
        person_store=person_store or make_person_store(),
        openrouter_client=client or AsyncMock(),
        settings=settings or make_settings(),
    )


# ── _safe_classification ──────────────────────────────────────────────────────

def test_safe_classification_accepts_valid():
    assert _safe_classification("personal") == "personal"
    assert _safe_classification("professional") == "professional"


def test_safe_classification_defaults_unknown():
    assert _safe_classification("executive") == "unknown"
    assert _safe_classification(None) == "unknown"
    assert _safe_classification(42) == "unknown"


# ── _format_batch ─────────────────────────────────────────────────────────────

def test_format_batch_includes_timestamp_and_content():
    row = make_episode_row()
    result = _format_batch([row])

    assert "2026-05-23" in result
    assert "João Silva" in result
    assert "Ze:" in result


def test_format_batch_uses_summary_over_response():
    row = make_episode_row(
        summary="Summary text here",
        response="Raw response that is much longer and should not appear",
    )
    result = _format_batch([row])

    assert "Summary text here" in result


def test_format_batch_falls_back_to_response_when_no_summary():
    row = make_episode_row(summary=None, response="Raw response content")
    result = _format_batch([row])

    assert "Raw response content" in result


def test_format_batch_separates_multiple_episodes():
    rows = [make_episode_row(), make_episode_row()]
    result = _format_batch(rows)

    assert "---" in result


# ── ContactsConsolidator.run — no episodes ────────────────────────────────────

async def test_run_returns_empty_report_when_no_episodes():
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[])
    consolidator = make_consolidator(pool=make_pool(conn))

    report = await consolidator.run()

    assert report.episodes_scanned == 0
    assert report.candidates_extracted == 0
    assert report.contacts_created == 0


# ── ContactsConsolidator.run — extraction ─────────────────────────────────────

async def test_run_creates_new_contact_when_not_found():
    episode = make_episode_row()
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[[episode], []])  # episodes, then mark_processed
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(return_value='[{"name": "João Silva", "classification": "professional", "relationship": "charter operator", "contact_info": {}, "confidence": 0.9, "context": "Called to validate H1"}]')

    store = make_person_store(get_by_name_result=[])
    consolidator = make_consolidator(pool=make_pool(conn), person_store=store, client=client)

    report = await consolidator.run()

    assert report.episodes_scanned == 1
    assert report.candidates_extracted == 1
    assert report.contacts_created == 1
    assert report.contacts_updated == 0
    store.upsert.assert_called_once()
    stored_person = store.upsert.call_args[0][0]
    assert stored_person.name == "João Silva"
    assert stored_person.classification == "professional"
    assert stored_person.confirmed is False


async def test_run_updates_existing_contact_when_found():
    episode = make_episode_row()
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[episode])
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(return_value='[{"name": "João Silva", "classification": "professional", "relationship": "charter operator", "contact_info": {}, "confidence": 0.9, "context": "Called again"}]')

    existing = Person(name="João Silva", id=uuid4(), confirmed=True, confidence=1.0)
    store = make_person_store(get_by_name_result=[existing])
    consolidator = make_consolidator(pool=make_pool(conn), person_store=store, client=client)

    report = await consolidator.run()

    assert report.contacts_created == 0
    assert report.contacts_updated == 1
    store.upsert.assert_not_called()
    store.add_source.assert_called_once()


async def test_run_skips_candidate_with_empty_name():
    episode = make_episode_row()
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[episode])
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(return_value='[{"name": "", "classification": "unknown", "relationship": "", "contact_info": {}, "confidence": 0.5, "context": ""}]')

    store = make_person_store()
    consolidator = make_consolidator(pool=make_pool(conn), person_store=store, client=client)

    report = await consolidator.run()

    assert report.contacts_created == 0
    store.upsert.assert_not_called()


async def test_run_handles_llm_failure_gracefully():
    episode = make_episode_row()
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[episode])
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("LLM timeout"))

    store = make_person_store()
    consolidator = make_consolidator(pool=make_pool(conn), person_store=store, client=client)

    report = await consolidator.run()

    assert report.candidates_extracted == 0
    assert report.contacts_created == 0
    store.upsert.assert_not_called()


async def test_run_handles_bad_json_gracefully():
    episode = make_episode_row()
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[episode])
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(return_value="not valid json at all")

    store = make_person_store()
    consolidator = make_consolidator(pool=make_pool(conn), person_store=store, client=client)

    report = await consolidator.run()

    assert report.candidates_extracted == 0


# ── Mark processed ────────────────────────────────────────────────────────────

async def test_run_marks_episodes_as_extracted():
    episode_id = uuid4()
    episode = make_episode_row(id=episode_id)
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[episode])
    conn.execute = AsyncMock()

    client = AsyncMock()
    client.complete = AsyncMock(return_value="[]")

    consolidator = make_consolidator(pool=make_pool(conn), client=client)
    await consolidator.run()

    assert conn.execute.called
    call_sql = conn.execute.call_args[0][0]
    assert "contacts_extracted = true" in call_sql
