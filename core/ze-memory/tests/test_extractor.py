"""Tests for ze_memory.extractor — event extraction functions."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from ze_memory.extractor import (
    extract_events,
    gather_event_proposals,
    parse_event_response,
    raw_to_events,
)
from ze_memory.types import Event


# ── parse_event_response ──────────────────────────────────────────────────────

def test_parse_event_response_valid_list():
    raw = json.dumps([
        {"title": "Team meeting", "event_type": "meeting"},
        {"title": "Dentist", "event_type": "appointment", "start_at": "2024-03-10T10:00:00"},
    ])
    result = parse_event_response(raw)
    assert len(result) == 2
    assert result[0]["title"] == "Team meeting"


def test_parse_event_response_strips_markdown_fence():
    raw = "```json\n[{\"title\": \"Call\", \"event_type\": \"call\"}]\n```"
    result = parse_event_response(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Call"


def test_parse_event_response_drops_items_without_title():
    raw = json.dumps([
        {"event_type": "meeting"},
        {"title": "Valid", "event_type": "call"},
    ])
    result = parse_event_response(raw)
    assert len(result) == 1
    assert result[0]["title"] == "Valid"


def test_parse_event_response_drops_items_without_event_type():
    raw = json.dumps([{"title": "No type"}])
    result = parse_event_response(raw)
    assert result == []


def test_parse_event_response_returns_empty_on_invalid_json():
    result = parse_event_response("not json")
    assert result == []


def test_parse_event_response_returns_empty_on_non_list():
    result = parse_event_response(json.dumps({"title": "Not a list"}))
    assert result == []


# ── raw_to_events ─────────────────────────────────────────────────────────────

def test_raw_to_events_basic():
    raw = [{"title": "Sprint planning", "event_type": "meeting"}]
    events = raw_to_events(raw)
    assert len(events) == 1
    assert isinstance(events[0], Event)
    assert events[0].title == "Sprint planning"
    assert events[0].event_type == "meeting"
    assert events[0].id is None


def test_raw_to_events_with_timestamps():
    raw = [{
        "title": "Flight to Lisbon",
        "event_type": "trip",
        "start_at": "2024-06-01T08:00:00Z",
        "end_at": "2024-06-01T10:00:00Z",
    }]
    events = raw_to_events(raw)
    assert events[0].start_at is not None
    assert events[0].end_at is not None


def test_raw_to_events_with_participants():
    raw = [{"title": "1:1", "event_type": "meeting", "participants": ["Alice", "Bob"]}]
    events = raw_to_events(raw)
    assert events[0].participant_names == ["Alice", "Bob"]


def test_raw_to_events_skips_invalid_items():
    raw = [
        {"event_type": "meeting"},
        {"title": "Valid", "event_type": "call"},
    ]
    events = raw_to_events(raw)
    assert len(events) == 1


def test_raw_to_events_empty_list():
    assert raw_to_events([]) == []


# ── extract_events ────────────────────────────────────────────────────────────

async def test_extract_events_calls_llm_and_parses():
    client = AsyncMock()
    client.complete = AsyncMock(return_value=json.dumps([
        {"title": "Weekly sync", "event_type": "meeting"},
    ]))

    events = await extract_events(client, prompt="meeting notes", response="We had a weekly sync.", model="test")

    client.complete.assert_called_once()
    assert len(events) == 1
    assert events[0].title == "Weekly sync"


async def test_extract_events_skips_error_responses():
    client = AsyncMock()
    events = await extract_events(client, prompt="hi", response="[ERROR] something went wrong", model="test")
    client.complete.assert_not_called()
    assert events == []


async def test_extract_events_returns_empty_on_llm_failure():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    events = await extract_events(client, prompt="hi", response="We met yesterday.", model="test")
    assert events == []


async def test_extract_events_returns_empty_on_bad_json():
    client = AsyncMock()
    client.complete = AsyncMock(return_value="not json")

    events = await extract_events(client, prompt="hi", response="We met.", model="test")
    assert events == []


# ── gather_event_proposals ────────────────────────────────────────────────────

async def test_gather_event_proposals_with_client():
    client = AsyncMock()
    client.complete = AsyncMock(return_value=json.dumps([
        {"title": "Dinner with Alice", "event_type": "dinner"},
    ]))

    configurable = {"openrouter_client": client}
    events = await gather_event_proposals(configurable, prompt="I had dinner", response="Nice dinner with Alice.")

    assert len(events) == 1
    assert events[0].title == "Dinner with Alice"


async def test_gather_event_proposals_without_client_returns_empty():
    events = await gather_event_proposals({}, prompt="hi", response="hello")
    assert events == []
