from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_personal.contacts.types import Person
from ze_browser import BrowserError, BrowserResult


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


def make_person_store(existing: list | None = None):
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=existing or [])
    store.upsert = AsyncMock(return_value=make_person())
    store.add_source = AsyncMock()
    return store


def make_campaign_store(outreach_id=None, latest_outreach_id=None):
    store = AsyncMock()
    store.add_outreach = AsyncMock(return_value=outreach_id or uuid4())
    store.increment_found = AsyncMock()
    store.save_draft = AsyncMock()
    store.get_latest_outreach_id = AsyncMock(return_value=latest_outreach_id or uuid4())
    store.log_outreach_event = AsyncMock()
    return store


# ── browser_extract ───────────────────────────────────────────────────────────

_DELAY_MS = 500
_MAX_CHARS = 10_000


async def test_browser_extract_tool_returns_text():
    from ze_browser.tool import browser_extract

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Test",
        text="A" * 100,
        status_code=200,
    ))

    with patch("ze_browser.tool.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )

    assert tc.success is True
    assert "A" in tc.result


async def test_browser_extract_tool_truncates_text():
    from ze_browser.tool import browser_extract

    long_text = "x" * 20_000
    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Test",
        text=long_text,
        status_code=200,
    ))

    with patch("ze_browser.tool.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )

    assert len(tc.result) <= _MAX_CHARS


async def test_browser_extract_blocked_returns_skip_msg():
    from ze_browser.tool import browser_extract, _BLOCKED_MSG

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(return_value=BrowserResult(
        url="https://example.com",
        title="Blocked",
        text="",
        status_code=403,
    ))

    with patch("ze_browser.tool.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )

    assert tc.result == _BLOCKED_MSG
    assert tc.success is True


async def test_browser_extract_tool_rate_limit():
    from ze_browser.tool import browser_extract

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

    with patch("ze_browser.tool.asyncio.sleep", side_effect=mock_sleep):
        await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )
        await browser_extract(
            url="https://example.com/2",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )

    assert len(sleep_calls) == 2


async def test_browser_extract_error_returns_error_string():
    from ze_browser.tool import browser_extract

    browser_client = AsyncMock()
    browser_client.extract = AsyncMock(side_effect=BrowserError("service down"))

    with patch("ze_browser.tool.asyncio.sleep"):
        tc = await browser_extract(
            url="https://example.com",
            browser_client=browser_client,
            browser_delay_ms=_DELAY_MS,
            browser_max_text_chars=_MAX_CHARS,
        )

    assert tc.success is False
    assert "service down" in tc.result


# ── add_prospect ──────────────────────────────────────────────────────────────

async def test_add_prospect_new_person():
    from ze_prospecting.agents.tools import add_prospect

    person_store = make_person_store(existing=[])
    cs = make_campaign_store()
    campaign_id = str(uuid4())

    result = await add_prospect(
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
        campaign_store=cs,
    )

    assert "Maria Santos" in result
    person_store.upsert.assert_called_once()
    person_store.add_source.assert_called()
    cs.add_outreach.assert_called_once()
    cs.increment_found.assert_called_once()


async def test_add_prospect_duplicate_adds_source():
    from ze_prospecting.agents.tools import add_prospect

    existing_person = make_person(name="Maria Santos")
    person_store = make_person_store(existing=[existing_person])
    cs = make_campaign_store(outreach_id=None)
    cs.add_outreach = AsyncMock(return_value=None)  # ON CONFLICT DO NOTHING
    campaign_id = str(uuid4())

    result = await add_prospect(
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
        campaign_store=cs,
    )

    assert "Maria Santos" in result
    person_store.upsert.assert_not_called()
    person_store.add_source.assert_called_once()
    cs.increment_found.assert_not_called()


async def test_add_prospect_stores_enrichment_notes():
    from ze_prospecting.agents.tools import add_prospect

    person_store = make_person_store(existing=[])
    upserted: list[Person] = []

    async def capture_upsert(person):
        upserted.append(person)
        return make_person(notes=person.notes)

    person_store.upsert = capture_upsert
    cs = make_campaign_store()

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
        campaign_store=cs,
    )

    assert upserted
    assert "found LinkedIn, no email" in upserted[0].notes


# ── draft_outreach ────────────────────────────────────────────────────────────

async def test_draft_outreach_tool():
    from ze_prospecting.agents.tools import draft_outreach

    person = make_person(name="João Silva")
    person_store = make_person_store(existing=[person])
    cs = make_campaign_store()
    campaign_id = str(uuid4())

    client = AsyncMock()
    client.complete = AsyncMock(return_value="Hi João, reaching out about charter opportunities...")

    result = await draft_outreach(
        name="João Silva",
        context="CEO of AirCharter, runs short-haul charter ops in Portugal",
        campaign_brief="Find charter operators in Portugal for partnership",
        channel="email",
        campaign_id=campaign_id,
        client=client,
        model="anthropic/claude-sonnet-4-5",
        person_store=person_store,
        campaign_store=cs,
    )

    assert "João" in result
    client.complete.assert_called_once()
    cs.save_draft.assert_called_once()


async def test_draft_outreach_no_contact_returns_error():
    from ze_prospecting.agents.tools import draft_outreach

    person_store = make_person_store(existing=[])
    cs = make_campaign_store()

    with pytest.raises(ValueError, match="No contact found"):
        await draft_outreach(
            name="Unknown Person",
            context="unknown",
            campaign_brief="test",
            channel="email",
            campaign_id=str(uuid4()),
            client=AsyncMock(),
            model="test",
            person_store=person_store,
            campaign_store=cs,
        )


# ── log_outreach_event ────────────────────────────────────────────────────────

async def test_log_outreach_event_sent():
    from ze_prospecting.agents.tools import log_outreach_event

    person = make_person(name="Maria Santos")
    person_store = make_person_store(existing=[person])
    outreach_id = uuid4()
    cs = make_campaign_store(latest_outreach_id=outreach_id)

    result = await log_outreach_event(
        contact_name="Maria Santos",
        event_type="sent",
        channel="email",
        notes="Sent intro email",
        campaign_store=cs,
        person_store=person_store,
    )

    assert "Maria Santos" in result
    cs.log_outreach_event.assert_called_once_with(outreach_id, "sent", "Sent intro email", "sent_at")


async def test_log_outreach_event_no_campaign_row_returns_not_a_prospect():
    from ze_prospecting.agents.tools import log_outreach_event

    person = make_person(name="Unknown Contact")
    person_store = make_person_store(existing=[person])
    cs = make_campaign_store()
    cs.get_latest_outreach_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not in any outreach campaign"):
        await log_outreach_event(
            contact_name="Unknown Contact",
            event_type="sent",
            channel="email",
            notes="Sent intro email",
            campaign_store=cs,
            person_store=person_store,
        )

    cs.log_outreach_event.assert_not_called()


async def test_log_outreach_event_ambiguous_returns_clarification():
    from ze_prospecting.agents.tools import log_outreach_event

    matches = [
        make_person(name="João Silva"),
        make_person(name="João Santos"),
    ]
    person_store = make_person_store(existing=matches)
    cs = make_campaign_store()

    with pytest.raises(ValueError, match="Ambiguous"):
        await log_outreach_event(
            contact_name="João",
            event_type="sent",
            channel="email",
            notes="Sent email",
            campaign_store=cs,
            person_store=person_store,
        )

    cs.get_latest_outreach_id.assert_not_called()


async def test_log_outreach_event_invalid_event_type_rejected():
    from ze_prospecting.agents.tools import log_outreach_event

    person_store = make_person_store(existing=[make_person(name="Maria Santos")])
    cs = make_campaign_store()

    with pytest.raises(ValueError, match="Invalid event_type"):
        await log_outreach_event(
            contact_name="Maria Santos",
            event_type="hacked",
            channel="email",
            notes="test",
            campaign_store=cs,
            person_store=person_store,
        )

    person_store.get_by_name.assert_not_called()
