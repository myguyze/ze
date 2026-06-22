from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4


from ze_personal.goals.planner import GoalPlanner
from ze_automation.goals.types import Goal, GoalStatus, GoalSuggestion, SuggestionStatus
from ze_sdk.memory import Episode, Fact


def _client(response: str = "{}"):
    m = AsyncMock()
    m.complete = AsyncMock(return_value=response)
    return m


def _planner(client):
    return GoalPlanner(client=client, model="test-model")


def _fact(key="language", value="User studies Spanish every morning before work") -> Fact:
    return Fact(predicate=key, value=value, confidence=0.9)


def _episode(summary="User mentioned wanting to visit Argentina in 2027") -> Episode:
    return Episode(
        agent="companion",
        prompt="Let's plan my trip",
        response="Sounds great!",
        summary=summary,
        created_at=datetime.now(timezone.utc),
    )


def _goal_with_retro(title="Travel to South America") -> Goal:
    g = Goal(
        id=uuid4(),
        title=title,
        objective="Visit South America",
        success_condition="Trip completed",
        status=GoalStatus.COMPLETED,
    )
    g.retrospective_text = (
        "Completed the trip to Argentina. Key finding: language barrier was a major issue. "
        "João struggled with Spanish throughout the trip."
    )
    return g


def _valid_suggestion_json(title="Learn Spanish", rationale=None) -> str:
    return json.dumps({
        "suggestion": {
            "title": title,
            "objective": "Achieve conversational fluency in Spanish within 6 months using daily practice and immersion.",
            "rationale": rationale or (
                "Based on your retrospective for 'Travel to South America', language barrier was "
                "identified as the main blocker during the trip to Argentina in 2024."
            ),
            "source_type": "retrospective",
            "source_ref": "Travel to South America",
        }
    })


# ── generate_suggestion: null / no signal ─────────────────────────────────────

async def test_generate_suggestion_returns_none_on_null_response():
    client = _client(json.dumps({"suggestion": None}))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()],
        episodes=[_episode()],
        retrospectives=[_goal_with_retro()],
        active_goal_titles=[],
    )

    assert result is None


async def test_generate_suggestion_returns_none_when_no_signal():
    client = _client(json.dumps({"suggestion": None}))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[],
        episodes=[],
        retrospectives=[],
        active_goal_titles=[],
    )

    assert result is None


# ── generate_suggestion: confidence gate ─────────────────────────────────────

async def test_generate_suggestion_returns_none_when_rationale_too_short():
    short_rationale = "User seems interested in Spanish."  # < 15 words, no proper nouns
    client = _client(json.dumps({
        "suggestion": {
            "title": "Learn Spanish",
            "objective": "Achieve conversational fluency in Spanish within 6 months.",
            "rationale": short_rationale,
            "source_type": "memory_facts",
            "source_ref": "language",
        }
    }))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()], episodes=[], retrospectives=[], active_goal_titles=[],
    )

    assert result is None


async def test_generate_suggestion_returns_none_when_rationale_generic():
    generic_rationale = "the user has mentioned this topic several times in recent conversations about goals"
    client = _client(json.dumps({
        "suggestion": {
            "title": "Learn Spanish",
            "objective": "Achieve conversational fluency in Spanish within 6 months of practice.",
            "rationale": generic_rationale,
            "source_type": "memory_facts",
            "source_ref": "language",
        }
    }))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()], episodes=[], retrospectives=[], active_goal_titles=[],
    )

    assert result is None


async def test_generate_suggestion_returns_none_on_malformed_json():
    client = _client("not valid json {{{")
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()], episodes=[], retrospectives=[], active_goal_titles=[],
    )

    assert result is None


async def test_generate_suggestion_returns_none_on_openrouter_error():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("OpenRouter 429"))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()], episodes=[], retrospectives=[], active_goal_titles=[],
    )

    assert result is None


async def test_generate_suggestion_skips_topic_matching_active_goal():
    client = _client(_valid_suggestion_json(title="Learn Spanish"))
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()],
        episodes=[_episode()],
        retrospectives=[_goal_with_retro()],
        active_goal_titles=["Learn Spanish"],
    )

    assert result is None


# ── generate_suggestion: happy path ──────────────────────────────────────────

async def test_generate_suggestion_returns_suggestion_on_valid_output():
    client = _client(_valid_suggestion_json())
    planner = _planner(client)

    result = await planner.generate_suggestion(
        memory_facts=[_fact()],
        episodes=[_episode()],
        retrospectives=[_goal_with_retro()],
        active_goal_titles=["Run a marathon"],
    )

    assert isinstance(result, GoalSuggestion)
    assert result.title == "Learn Spanish"
    assert result.status == SuggestionStatus.PENDING
    assert result.id is not None
    assert result.suggested_at is not None


# ── create_goal_from_suggestion ───────────────────────────────────────────────

def test_create_goal_from_suggestion_maps_fields_correctly():
    client = AsyncMock()
    planner = GoalPlanner(client=client, model="test-model")

    suggestion = GoalSuggestion(
        id=uuid4(),
        title="Learn Spanish",
        objective="Achieve conversational fluency in Spanish within 6 months.",
        rationale="Based on retrospective for Travel to South America in 2024.",
        source_type="retrospective",
        source_ref="Travel to South America",
        status=SuggestionStatus.PENDING,
        suggested_at=datetime.now(timezone.utc),
    )

    goal = planner.create_goal_from_suggestion(suggestion)

    assert goal.title == "Learn Spanish"
    assert goal.objective == suggestion.objective
    assert goal.status == GoalStatus.ACTIVE
    assert goal.type == "suggested"
    assert goal.id is None  # not yet persisted
