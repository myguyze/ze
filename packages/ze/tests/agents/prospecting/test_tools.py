from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze.agents.types import ToolCall
from ze.contacts.types import Person
from ze_browser import BrowserError, BrowserResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings(**overrides):
    import pathlib
    from ze.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    defaults = dict(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def make_person(**overrides):
    now = datetime.utcnow()
    defaults = dict(
        id=uuid4(),
        name="João Silva",
        aliases=[],
        classification="professional",
        classification_confidence=0.6,
        relationship_to_user="charter operator",
        contact_info={},
        notes="",
        confirmed=False,
        dismissed=False,
        confidence=0.2,
        first_seen=now,
        last_mentioned=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Person(**defaults)


def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
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


def make_person_store(existing: list | None = None):
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=existing or [])
    store.upsert = AsyncMock(return_value=make_person())
    store.add_source = AsyncMock()
    return store


# ── browser_extract ───────────────────────────────────────────────────────────

async def test_browser_extract_tool_returns_text():
    from ze.tools.browser import browser_extract
    settings = make_settings()

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Test",
        text="A" * 100,
        status_code=200,
    ))

    with patch("ze.tools.browser.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            settings=settings,
        )

    assert tc.success is True
    assert "A" in tc.result


async def test_browser_extract_tool_truncates_text():
    from ze.tools.browser import browser_extract
    settings = make_settings()

    long_text = "x" * 20_000
    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Test",
        text=long_text,
        status_code=200,
    ))

    with patch("ze.tools.browser.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            settings=settings,
        )

    assert len(tc.result) <= settings.browser_max_text_chars


async def test_browser_extract_blocked_returns_skip_msg():
    from ze.tools.browser import browser_extract, _BLOCKED_MSG
    settings = make_settings()

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Blocked",
        text="",
        status_code=403,
    ))

    with patch("ze.tools.browser.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            settings=settings,
        )

    assert tc.result == _BLOCKED_MSG
    assert tc.success is True


async def test_browser_extract_tool_rate_limit():
    from ze.tools.browser import browser_extract
    settings = make_settings()

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Test",
        text="hello",
        status_code=200,
    ))

    sleep_calls: list = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch("ze.tools.browser.asyncio.sleep", side_effect=mock_sleep):
        await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            settings=settings,
        )
        await browser_extract(
            url="https://example.com/2",
            browser_client=browser_client,
            settings=settings,
        )

    assert len(sleep_calls) == 2


async def test_browser_extract_error_returns_error_string():
    from ze.tools.browser import browser_extract
    settings = make_settings()

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(side_effect=BrowserError("service down"))

    with patch("ze.tools.browser.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            settings=settings,
        )

    assert tc.success is False
    assert "service down" in tc.result


# ── add_prospect ──────────────────────────────────────────────────────────────

async def test_add_prospect_new_person():
    from ze.tools.prospecting import add_prospect

    person_store = make_person_store(existing=[])
    pool = make_pool()
    campaign_id = str(uuid4())

    tc = await add_prospect(
        name="Maria Santos",
        company="AirCharter PT",
        role="CEO",
        relationship="charter operator",
        contact_info={"email": "maria@aircharter.pt"},
        source_url="https://aircharter.pt/about",
        enrichment_notes="email found on website",
        campaign_id=campaign_id,
        channel="email",
        person_store=person_store,
        pool=pool,
    )

    assert tc.success is True
    person_store.upsert.assert_called_once()
    person_store.add_source.assert_called()


async def test_add_prospect_duplicate_adds_source():
    from ze.tools.prospecting import add_prospect

    existing_person = make_person(name="Maria Santos")
    person_store = make_person_store(existing=[existing_person])
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # ON CONFLICT DO NOTHING
    pool = make_pool(conn)
    campaign_id = str(uuid4())

    tc = await add_prospect(
        name="Maria Santos",
        company=None,
        role=None,
        relationship="charter operator",
        contact_info={},
        source_url="https://example.com",
        enrichment_notes="found via LinkedIn",
        campaign_id=campaign_id,
        channel="linkedin",
        person_store=person_store,
        pool=pool,
    )

    assert tc.success is True
    person_store.upsert.assert_not_called()
    person_store.add_source.assert_called_once()


async def test_add_prospect_stores_enrichment_notes():
    from ze.tools.prospecting import add_prospect

    person_store = make_person_store(existing=[])
    upserted: list[Person] = []

    async def capture_upsert(person):
        upserted.append(person)
        return make_person(notes=person.notes)

    person_store.upsert = capture_upsert
    pool = make_pool()

    await add_prospect(
        name="Carlos Ferreira",
        company="TAP",
        role="Ops Manager",
        relationship="aviation contact",
        contact_info={},
        source_url="https://tap.pt",
        enrichment_notes="found LinkedIn, no email",
        campaign_id=str(uuid4()),
        channel="linkedin",
        person_store=person_store,
        pool=pool,
    )

    assert upserted
    assert "found LinkedIn, no email" in upserted[0].notes


# ── draft_outreach ────────────────────────────────────────────────────────────

async def test_draft_outreach_tool():
    from ze.tools.prospecting import draft_outreach

    person = make_person(name="João Silva")
    person_store = make_person_store(existing=[person])
    pool = make_pool()
    campaign_id = str(uuid4())

    client = AsyncMock()
    client.complete = AsyncMock(return_value="Hi João, reaching out about charter opportunities...")

    tc = await draft_outreach(
        name="João Silva",
        context="CEO of AirCharter, runs short-haul charter ops in Portugal",
        campaign_brief="Find charter operators in Portugal for partnership",
        channel="email",
        campaign_id=campaign_id,
        client=client,
        model="anthropic/claude-sonnet-4-5",
        person_store=person_store,
        pool=pool,
    )

    assert tc.success is True
    assert "João" in tc.result
    client.complete.assert_called_once()


async def test_draft_outreach_no_contact_returns_error():
    from ze.tools.prospecting import draft_outreach

    person_store = make_person_store(existing=[])
    pool = make_pool()

    tc = await draft_outreach(
        name="Unknown Person",
        context="unknown",
        campaign_brief="test",
        channel="email",
        campaign_id=str(uuid4()),
        client=AsyncMock(),
        model="test",
        person_store=person_store,
        pool=pool,
    )

    assert tc.success is False
    assert "No contact found" in tc.result


# ── log_outreach_event ────────────────────────────────────────────────────────

async def test_log_outreach_event_sent():
    from ze.tools.prospecting import log_outreach_event

    person = make_person(name="Maria Santos")
    person_store = make_person_store(existing=[person])

    outreach_id = uuid4()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": outreach_id})
    pool = make_pool(conn)

    tc = await log_outreach_event(
        contact_name="Maria Santos",
        event_type="sent",
        channel="email",
        notes="Sent intro email",
        pool=pool,
        person_store=person_store,
    )

    assert tc.success is True
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args[0][0]
    assert "UPDATE prospect_outreach" in call_sql
    assert "sent_at" in call_sql


async def test_log_outreach_event_no_match_creates_standalone():
    from ze.tools.prospecting import log_outreach_event

    person = make_person(name="Unknown Contact")
    person_store = make_person_store(existing=[person])

    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = make_pool(conn)

    tc = await log_outreach_event(
        contact_name="Unknown Contact",
        event_type="sent",
        channel="email",
        notes="Sent intro email",
        pool=pool,
        person_store=person_store,
    )

    assert tc.success is True
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args[0][0]
    assert "INSERT INTO prospect_outreach" in call_sql


async def test_log_outreach_event_ambiguous_returns_clarification():
    from ze.tools.prospecting import log_outreach_event

    matches = [
        make_person(name="João Silva"),
        make_person(name="João Santos"),
    ]
    person_store = make_person_store(existing=matches)
    pool = make_pool()

    tc = await log_outreach_event(
        contact_name="João",
        event_type="sent",
        channel="email",
        notes="Sent email",
        pool=pool,
        person_store=person_store,
    )

    assert tc.success is False
    assert "Ambiguous" in tc.result
    pool.acquire.assert_not_called()


async def test_log_outreach_event_invalid_event_type_rejected():
    from ze.tools.prospecting import log_outreach_event

    person_store = make_person_store(existing=[make_person(name="Maria Santos")])
    pool = make_pool()

    tc = await log_outreach_event(
        contact_name="Maria Santos",
        event_type="hacked",
        channel="email",
        notes="test",
        pool=pool,
        person_store=person_store,
    )

    assert tc.success is False
    assert "invalid event_type" in tc.error
    pool.acquire.assert_not_called()
    person_store.get_by_name.assert_not_called()
