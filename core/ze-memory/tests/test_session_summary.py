"""Unit tests for SessionSummariser (Phase 65 — Eager Session Summaries)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from ze_memory.session_summary import SessionSummariser, _is_excluded_session


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_summariser(settings=None, enabled=True):
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=AsyncMock(
            fetch=AsyncMock(return_value=[]),
            execute=AsyncMock(),
        )),
        __aexit__=AsyncMock(return_value=False),
    ))
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=[0.1] * 384)
    client = AsyncMock()
    client.complete = AsyncMock(return_value="A brief session summary.")
    if settings is None:
        settings = {"memory": {"session_summary": {"enabled": enabled}}}
    return SessionSummariser(pool=pool, embedder=embedder, openrouter_client=client, settings=settings)


def _make_episode(prompt="hello", response="world", agent="companion", created_at=None):
    import datetime
    row = {
        "agent": agent,
        "prompt": prompt,
        "response": response,
        "created_at": created_at or datetime.datetime(2026, 6, 1, 10, 0),
    }
    return row


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_disabled_returns_zero():
    summariser = _make_summariser(enabled=False)
    result = await summariser.run()
    assert result == 0


async def test_no_candidates_returns_zero():
    summariser = _make_summariser()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    summariser._pool = pool
    result = await summariser.run()
    assert result == 0


def test_transcript_truncates_oldest_first():
    summariser = _make_summariser()
    episodes = [
        _make_episode(prompt="A" * 1000, response="B" * 1000),
        _make_episode(prompt="C" * 100, response="D" * 100),
        _make_episode(prompt="E" * 10, response="F" * 10),
    ]
    # max_tokens set to 200 — only the newest two turns should survive
    transcript = summariser._build_transcript(episodes, max_tokens=200)
    assert "E" * 10 in transcript
    assert "A" * 1000 not in transcript


def test_transcript_all_turns_fit():
    summariser = _make_summariser()
    episodes = [_make_episode(prompt="hi", response="hello")]
    transcript = summariser._build_transcript(episodes, max_tokens=10000)
    assert "hi" in transcript
    assert "hello" in transcript


def test_build_transcript_empty_overflow():
    """When every turn is too large even alone, return empty string (guard)."""
    summariser = _make_summariser()
    episodes = [_make_episode(prompt="x" * 100000, response="y" * 100000)]
    transcript = summariser._build_transcript(episodes, max_tokens=1)
    assert transcript == ""


async def test_llm_error_skips_session():
    summariser = _make_summariser()
    summariser._client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    import datetime
    candidates = [{"session_id": "sess-1", "last_turn_at": datetime.datetime(2026, 6, 1)}]
    episodes = [_make_episode(), _make_episode()]

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[candidates, episodes])
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    summariser._pool = pool

    result = await summariser.run()
    assert result == 0
    conn.execute.assert_not_called()


def test_excluded_session_ids():
    assert _is_excluded_session("")
    assert _is_excluded_session("migrated")
    assert _is_excluded_session("consolidator")
    assert _is_excluded_session("workflow:abc")
    assert _is_excluded_session("eval-20260601")
    assert not _is_excluded_session("user-session-1")
    assert not _is_excluded_session("normal-chat")
