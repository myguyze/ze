"""
Ze Eval Runner — CLI tool for running the eval suite against a live Ze instance.

Usage:
  uv run python evals/runner.py                    # routing accuracy only (cheap)
  uv run python evals/runner.py --judge            # + LLM quality scores
  uv run python evals/runner.py --tag routing      # filter by tag
  uv run python evals/runner.py --judge --tag companion --judge-model anthropic/claude-haiku-4-5

Environment variables (or pass as flags):
  ZE_EVAL_URL        Ze server base URL (default: http://localhost:8000)
  ZE_API_KEY         Ze API key
  OPENROUTER_API_KEY Required only when --judge is set

Results are saved to evals/results/<timestamp>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from evals.judge import DEFAULT_JUDGE_MODEL, judge

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_RESULTS_DIR = Path(__file__).parent / "results"


# ── Scenario loading ──────────────────────────────────────────────────────────

def load_scenarios(tag: str = "") -> list[dict]:
    scenarios: list[dict] = []
    for path in sorted(_SCENARIOS_DIR.glob("*.yaml")):
        items = yaml.safe_load(path.read_text()) or []
        for item in items:
            item.setdefault("file", path.stem)
            scenarios.append(item)
    if tag:
        scenarios = [s for s in scenarios if tag in s.get("tags", [])]
    return scenarios


# ── Ze chat ───────────────────────────────────────────────────────────────────

async def _chat(prompt: str, session_id: str, ze_url: str, ze_key: str) -> dict:
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{ze_url.rstrip('/')}/eval/chat",
            json={"prompt": prompt, "session_id": session_id},
            headers={"x-ze-api-key": ze_key},
        )
        resp.raise_for_status()
        return resp.json()


async def _run_turns(scenario: dict, session_id: str, ze_url: str, ze_key: str) -> dict:
    turns = scenario.get("turns")
    if turns:
        turn_results = []
        for i, turn in enumerate(turns):
            result = await _chat(turn["prompt"], session_id, ze_url, ze_key)
            turn_results.append({"turn": i + 1, "prompt": turn["prompt"], "result": result})
        final_agent = turn_results[-1]["result"].get("agent_used") if turn_results else None
        final_response = turn_results[-1]["result"].get("response", "") if turn_results else ""
        return {"turns": turn_results, "agent_used": final_agent, "response": final_response}
    result = await _chat(scenario["prompt"], session_id, ze_url, ze_key)
    return result


# ── Scoring ───────────────────────────────────────────────────────────────────

def _routing_correct(scenario: dict, agent_used: str | None) -> bool | None:
    expected = scenario.get("expected_agent")
    if not expected or not agent_used:
        return None
    return agent_used == expected


def _collect_tool_calls(ze_result: dict) -> list[dict]:
    """Gather tool calls from a single-turn or multi-turn result."""
    turns = ze_result.get("turns")
    if turns:
        calls: list[dict] = []
        for turn in turns:
            calls.extend(turn["result"].get("tool_calls", []))
        return calls
    return ze_result.get("tool_calls", [])


def _tools_correct(scenario: dict, ze_result: dict) -> bool | None:
    """
    Check that every tool listed in expected_tools was called and succeeded.
    Returns None when the scenario declares no expected_tools.
    """
    expected = scenario.get("expected_tools")
    if not expected:
        return None
    calls = _collect_tool_calls(ze_result)
    succeeded = {tc["tool_name"] for tc in calls if tc.get("success")}
    return all(t in succeeded for t in expected)


# ── Printing ──────────────────────────────────────────────────────────────────

_W_ID = 42
_W_AGENT = 12
_TICK = "✓"
_CROSS = "✗"
_DASH = "-"


def _sym(val: bool | None) -> str:
    if val is True:
        return _TICK
    if val is False:
        return _CROSS
    return _DASH


def _fmt_score(val: int | None) -> str:
    return str(val) if val is not None else _DASH


def _print_header(use_judge: bool) -> None:
    if use_judge:
        header = f"{'Scenario':<{_W_ID}}  {'Agent':<{_W_AGENT}}  {'Route':6}  {'Tools':6}  {'Qual':5}  {'Tone':5}  {'T.Use':5}  Pass"
    else:
        header = f"{'Scenario':<{_W_ID}}  {'Agent':<{_W_AGENT}}  {'Route':6}  {'Tools':6}  Error"
    print(header)
    print("─" * len(header))


def _print_row(
    scenario_id: str,
    agent_used: str | None,
    routing: bool | None,
    tools: bool | None,
    judge_score: dict | None,
    error: str | None,
) -> None:
    sid = scenario_id[:_W_ID]
    agent = (agent_used or "?")[:_W_AGENT]
    route_sym = _sym(routing)
    tools_sym = _sym(tools)

    if error:
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {'ERR':6}  {tools_sym:6}  {error[:50]}")
        return

    if judge_score:
        q = _fmt_score(judge_score.get("quality"))
        t = _fmt_score(judge_score.get("tone"))
        tu = _fmt_score(judge_score.get("tool_use"))
        p = _TICK if judge_score.get("pass") else _CROSS
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {route_sym:6}  {tools_sym:6}  {q:5}  {t:5}  {tu:5}  {p}")
    else:
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {route_sym:6}  {tools_sym:6}")


def _print_summary(run: dict) -> None:
    t = run["totals"]
    print()
    print("Summary")
    print("─" * 40)
    print(f"  Total scenarios:     {t['total']}")
    print(f"  Errors:              {t['errors']}")

    if t["total"] - t["errors"] > 0:
        rt_total = t["routing_correct"] + t["routing_wrong"]
        if rt_total > 0:
            print(f"  Routing correct:     {t['routing_correct']}/{rt_total} ({100*t['routing_correct']//rt_total}%)")
        print(f"  Routing unchecked:   {t['routing_unchecked']}")

        tl_total = t["tools_correct"] + t["tools_wrong"]
        if tl_total > 0:
            print(f"  Tools correct:       {t['tools_correct']}/{tl_total} ({100*t['tools_correct']//tl_total}%)")
        if t.get("tools_unchecked", 0) > 0:
            print(f"  Tools unchecked:     {t['tools_unchecked']}")

    if t.get("judged", 0) > 0:
        print()
        print(f"  Judged:              {t['judged']}")
        print(f"  Passed:              {t['passed']}/{t['judged']}")
        if t.get("avg_quality"):
            print(f"  Avg quality:         {t['avg_quality']:.1f}/5")
        if t.get("avg_tone"):
            print(f"  Avg tone:            {t['avg_tone']:.1f}/5")
        if t.get("avg_tool_use"):
            print(f"  Avg tool use:        {t['avg_tool_use']:.1f}/5")

    by_agent = run.get("by_agent", {})
    if by_agent:
        print()
        print("  By agent:")
        for agent, stats in sorted(by_agent.items()):
            judged = stats.get("judged", 0)
            passed = stats.get("passed", 0)
            rt_c = stats.get("routing_correct", 0)
            rt_w = stats.get("routing_wrong", 0)
            rt_total_a = rt_c + rt_w
            tl_c = stats.get("tools_correct", 0)
            tl_w = stats.get("tools_wrong", 0)
            tl_total_a = tl_c + tl_w
            rt_str = f"  routing {rt_c}/{rt_total_a}" if rt_total_a > 0 else ""
            tl_str = f"  tools {tl_c}/{tl_total_a}" if tl_total_a > 0 else ""
            judge_str = f"  passed {passed}/{judged}" if judged > 0 else ""
            q = stats.get("avg_quality")
            q_str = f"  quality {q:.1f}" if q else ""
            print(f"    {agent:<14} {stats['total']:3} scenarios{rt_str}{tl_str}{judge_str}{q_str}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> dict:
    ze_url = args.ze_url or os.environ.get("ZE_EVAL_URL", "http://localhost:8000")
    ze_key = args.ze_key or os.environ.get("ZE_API_KEY", "")
    or_key = args.or_key or os.environ.get("OPENROUTER_API_KEY", "")
    use_judge = args.judge

    if use_judge and not or_key:
        print("ERROR: --judge requires OPENROUTER_API_KEY env var or --or-key", file=sys.stderr)
        sys.exit(1)

    scenarios = load_scenarios(args.tag)
    if not scenarios:
        print(f"No scenarios found{' for tag: ' + args.tag if args.tag else ''}.", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now(UTC)
    run_id = ts.strftime("%Y-%m-%dT%H-%M-%S")

    print(f"Ze Eval — {ts.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Ze:   {ze_url}")
    print(f"Tag:  {args.tag or 'all'}")
    if use_judge:
        print(f"Judge: {args.judge_model}")
    print()
    _print_header(use_judge)

    results = []
    by_agent: dict[str, dict] = {}

    for scenario in scenarios:
        sid = scenario["id"]
        session_id = f"eval-{sid}-{run_id}"
        error: str | None = None
        ze_result: dict = {}
        judge_score: dict | None = None
        routing: bool | None = None

        try:
            ze_result = await _run_turns(scenario, session_id, ze_url, ze_key)
            error = ze_result.get("error")
        except Exception as exc:
            error = str(exc)

        agent_used = ze_result.get("agent_used") if not error else None

        tools: bool | None = None
        if not error:
            routing = _routing_correct(scenario, agent_used)
            tools = _tools_correct(scenario, ze_result)

            if use_judge and scenario.get("criteria"):
                # For multi-turn, judge the final response
                turns = ze_result.get("turns")
                if turns:
                    prompt_for_judge = " → ".join(t["prompt"] for t in turns)
                    response_for_judge = turns[-1]["result"].get("response", "")
                else:
                    prompt_for_judge = scenario.get("prompt", "")
                    response_for_judge = ze_result.get("response", "")

                try:
                    score = await judge(
                        description=scenario.get("description", sid),
                        prompt=prompt_for_judge,
                        response=response_for_judge,
                        expected_agent=scenario.get("expected_agent"),
                        agent_used=agent_used,
                        criteria=scenario["criteria"],
                        model=args.judge_model,
                        api_key=or_key,
                    )
                    judge_score = score.to_dict()
                except Exception as exc:
                    judge_score = {"error": str(exc)}

        _print_row(sid, agent_used, routing, tools, judge_score if judge_score and "error" not in judge_score else None, error)

        agent_key = agent_used or scenario.get("expected_agent") or "unknown"
        if agent_key not in by_agent:
            by_agent[agent_key] = {
                "total": 0,
                "routing_correct": 0, "routing_wrong": 0,
                "tools_correct": 0, "tools_wrong": 0,
                "judged": 0, "passed": 0, "quality_sum": 0,
            }
        by_agent[agent_key]["total"] += 1
        if routing is True:
            by_agent[agent_key]["routing_correct"] += 1
        elif routing is False:
            by_agent[agent_key]["routing_wrong"] += 1
        if tools is True:
            by_agent[agent_key]["tools_correct"] += 1
        elif tools is False:
            by_agent[agent_key]["tools_wrong"] += 1
        if judge_score and "error" not in judge_score:
            by_agent[agent_key]["judged"] += 1
            if judge_score.get("pass"):
                by_agent[agent_key]["passed"] += 1
            by_agent[agent_key]["quality_sum"] += judge_score.get("quality", 0)

        results.append({
            "scenario_id": sid,
            "scenario": scenario,
            "ze_result": ze_result,
            "agent_used": agent_used,
            "routing_correct": routing,
            "tools_correct": tools,
            "judge": judge_score,
            "error": error,
        })

    # Aggregate totals
    judged_results = [r for r in results if r["judge"] and "error" not in r["judge"]]
    quality_vals = [r["judge"]["quality"] for r in judged_results if r["judge"].get("quality")]
    tone_vals = [r["judge"]["tone"] for r in judged_results if r["judge"].get("tone")]
    tool_vals = [r["judge"]["tool_use"] for r in judged_results if r["judge"] and r["judge"].get("tool_use") is not None]

    for agent_key, stats in by_agent.items():
        if stats["judged"] > 0:
            stats["avg_quality"] = stats["quality_sum"] / stats["judged"]
        del stats["quality_sum"]

    run_data = {
        "run_id": run_id,
        "timestamp": ts.isoformat(),
        "ze_url": ze_url,
        "tag": args.tag or "",
        "judge_model": args.judge_model if use_judge else None,
        "totals": {
            "total": len(results),
            "errors": sum(1 for r in results if r["error"]),
            "routing_correct": sum(1 for r in results if r["routing_correct"] is True),
            "routing_wrong": sum(1 for r in results if r["routing_correct"] is False),
            "routing_unchecked": sum(1 for r in results if r["routing_correct"] is None),
            "tools_correct": sum(1 for r in results if r["tools_correct"] is True),
            "tools_wrong": sum(1 for r in results if r["tools_correct"] is False),
            "tools_unchecked": sum(1 for r in results if r["tools_correct"] is None),
            "judged": len(judged_results),
            "passed": sum(1 for r in judged_results if r["judge"].get("pass")),
            "avg_quality": sum(quality_vals) / len(quality_vals) if quality_vals else None,
            "avg_tone": sum(tone_vals) / len(tone_vals) if tone_vals else None,
            "avg_tool_use": sum(tool_vals) / len(tool_vals) if tool_vals else None,
        },
        "by_agent": by_agent,
        "results": results,
    }

    _print_summary(run_data)

    _RESULTS_DIR.mkdir(exist_ok=True)
    out_path = _RESULTS_DIR / f"{run_id}.json"
    out_path.write_text(json.dumps(run_data, indent=2, default=str))
    print(f"\nSaved: {out_path}")

    return run_data


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ze eval runner")
    p.add_argument("--tag", default="", help="Filter scenarios by tag")
    p.add_argument("--judge", action="store_true", help="Run LLM quality judge (costs tokens)")
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Model to use for judging")
    p.add_argument("--ze-url", default="", help="Ze server URL (default: $ZE_EVAL_URL or http://localhost:8000)")
    p.add_argument("--ze-key", default="", help="Ze API key (default: $ZE_API_KEY)")
    p.add_argument("--or-key", default="", help="OpenRouter API key (default: $OPENROUTER_API_KEY)")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(_parse_args()))
