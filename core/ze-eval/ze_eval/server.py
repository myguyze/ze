"""
Ze Eval MCP Server

Exposes Ze's eval endpoint as MCP tools so any LLM-powered IDE
(Claude Code, Cursor, Codex) can interactively send messages to Ze,
inspect routing decisions, and evaluate responses.

Configuration (via environment variables):
  ZE_EVAL_URL  — base URL of the Ze server (default: http://localhost:8000)
  ZE_API_KEY   — API key for the eval endpoint

Usage:
  python eval/server.py

The server definition is committed in .claude/settings.json. To activate it,
create .claude/settings.local.json (gitignored) with your key:

  {
    "mcpServers": {
      "ze-eval": {
        "env": { "ZE_API_KEY": "<your key from .env>" }
      }
    }
  }

Then start a new Claude Code session. See docs/eval.md for full setup instructions.
"""
from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

from ze_eval.scenario import load_scenarios

_ZE_EVAL_URL = os.getenv("ZE_EVAL_URL", "http://localhost:8000")
_ZE_API_KEY = os.getenv("ZE_API_KEY", "")
_HEADERS = {"x-ze-api-key": _ZE_API_KEY}

mcp = FastMCP("Ze Eval")


async def _do_chat(prompt: str, session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{_ZE_EVAL_URL}/eval/chat",
            json={"prompt": prompt, "session_id": session_id},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def _run_scenario_turns(scenario: dict, session_id: str) -> dict:
    turns = scenario.get("turns")
    if turns:
        turn_results = []
        for i, turn in enumerate(turns):
            result = await _do_chat(turn["prompt"], session_id)
            turn_results.append({
                "turn": i + 1,
                "prompt": turn["prompt"],
                "description": turn.get("description", ""),
                "result": result,
            })
        final_agent = turn_results[-1]["result"].get("agent_used") if turn_results else None
        return {"turns": turn_results, "agent_used": final_agent}
    return await _do_chat(scenario["prompt"], session_id)


@mcp.tool()
async def ze_chat(prompt: str, session_id: str = "eval") -> str:
    """
    Send a message to Ze and receive its full response with routing metadata.

    Returns JSON with:
      - response: Ze's text response
      - agent_used: which agent handled the request (e.g. "companion", "research")
      - routing: { primary_agent, confidence, routing_method, is_compound, score_gap, raw_scores }
      - pending_confirmation: true if Ze would pause to ask the user for confirmation
      - error: error message if the graph failed

    Use session_id to simulate multi-turn conversations (same ID = shared history).
    Each unique session_id gets its own conversation thread.
    """
    result = await _do_chat(prompt, session_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def ze_list_scenarios(tag: str = "") -> str:
    """
    List all available test scenarios from eval/scenarios/.

    Returns a JSON array of scenario objects, each with:
      - id: unique identifier
      - prompt: the message that will be sent to Ze
      - description: what this scenario is testing
      - expected_agent: the agent Ze should route to (optional)
      - tags: list of category tags
      - criteria: list of evaluation rubric items (optional)

    Optionally filter by tag (e.g. "companion", "routing", "persona").
    """
    scenarios = load_scenarios(tag=tag)
    return json.dumps(scenarios, indent=2)


@mcp.tool()
async def ze_run_scenario(scenario_id: str) -> str:
    """
    Run a named test scenario against Ze and return the result alongside the scenario definition.

    Supports both single-turn scenarios (with a top-level 'prompt') and multi-turn scenarios
    (with a 'turns' array of {prompt, description} objects). Multi-turn scenarios use the
    same session_id across turns to maintain conversation context.

    Returns JSON with:
      - scenario: the full scenario definition (prompt/turns, expected_agent, criteria, etc.)
      - result: Ze's response(s) and routing metadata
      - matches_expected_agent: true if Ze used the expected agent (null if no expectation set)
      - tool_calls: list of tools invoked during execution (name, args, duration_ms, success)
      - tokens_used: total tokens consumed
      - memory_proposals_count: number of memory facts proposed for storage

    You (the evaluator) should read the criteria and judge whether Ze's response passes.
    """
    from ze_eval.scenario import load_scenario_by_id
    scenario = load_scenario_by_id(scenario_id)
    if scenario is None:
        return json.dumps({"error": f"Scenario '{scenario_id}' not found"})

    result = await _run_scenario_turns(scenario, f"eval-{scenario_id}")

    matches = None
    expected = scenario.get("expected_agent")
    if expected:
        agent_used = result.get("agent_used")
        if agent_used:
            matches = agent_used == expected

    return json.dumps({"scenario": scenario, "result": result, "matches_expected_agent": matches}, indent=2)


@mcp.tool()
async def ze_run_suite(tag: str = "") -> str:
    """
    Run all test scenarios (optionally filtered by tag) against Ze.

    Supports both single-turn and multi-turn scenarios. Multi-turn scenarios
    send each turn sequentially and return all turn results in order.

    Returns a JSON summary with:
      - total, routing_correct, routing_wrong, routing_unchecked, errors counts
      - results: per-scenario objects with scenario definition, Ze's response(s),
        routing metadata, tool_calls, tokens_used, and memory_proposals_count

    Use this to get a broad picture of Ze's current behaviour before making changes,
    then run again after to detect regressions.

    Available tags: companion, routing, persona, research, reminders, memory,
    edge_case, multi_turn, emotional, safety, compound, graceful_degradation.
    """
    scenarios = load_scenarios(tag=tag)

    results = []
    for scenario in scenarios:
        result = await _run_scenario_turns(scenario, f"eval-{scenario['id']}")
        matches = None
        expected = scenario.get("expected_agent")
        if expected:
            agent_used = result.get("agent_used")
            if agent_used:
                matches = agent_used == expected
        results.append({"scenario": scenario, "result": result, "matches_expected_agent": matches})

    summary = {
        "total": len(results),
        "routing_correct": sum(1 for r in results if r["matches_expected_agent"] is True),
        "routing_wrong": sum(1 for r in results if r["matches_expected_agent"] is False),
        "routing_unchecked": sum(1 for r in results if r["matches_expected_agent"] is None),
        "errors": sum(1 for r in results if r["result"].get("error")),
        "results": results,
    }
    return json.dumps(summary, indent=2)


def serve() -> None:
    mcp.run()


if __name__ == "__main__":
    serve()
