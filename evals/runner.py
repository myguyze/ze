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
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from evals.judge import DEFAULT_JUDGE_MODEL, judge
from evals.metrics import fetch_session_metrics
from evals.verifier import outcome_correct as _outcome_correct
from evals.verifier import run_verification

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


def _match_args(actual: dict, expected_args: dict) -> bool:
    """Return True if actual tool args satisfy all expected_args conditions."""
    for key, value in expected_args.items():
        if key.endswith("__icontains"):
            col = key[: -len("__icontains")]
            actual_val = actual.get(col)
            if actual_val is None or str(value).lower() not in str(actual_val).lower():
                return False
        elif key.endswith("__contains"):
            col = key[: -len("__contains")]
            actual_val = actual.get(col)
            if actual_val is None or str(value) not in str(actual_val):
                return False
        elif key.endswith("__gte"):
            col = key[: -len("__gte")]
            actual_val = actual.get(col)
            if actual_val is None or str(actual_val) < str(value):
                return False
        elif key.endswith("__lte"):
            col = key[: -len("__lte")]
            actual_val = actual.get(col)
            if actual_val is None or str(actual_val) > str(value):
                return False
        else:
            if actual.get(key) != value:
                return False
    return True


def _tools_correct(scenario: dict, ze_result: dict) -> bool | None:
    """
    Check that every tool listed in expected_tools was called and succeeded.

    Each entry may be a bare string (name only) or a dict with 'name' and optional
    'args' conditions. Returns None when the scenario declares no expected_tools.
    """
    expected = scenario.get("expected_tools")
    if not expected:
        return None
    calls = _collect_tool_calls(ze_result)

    for entry in expected:
        if isinstance(entry, str):
            tool_name = entry
            expected_args = None
        else:
            tool_name = entry["name"]
            expected_args = entry.get("args")

        successful_calls = [tc for tc in calls if tc.get("tool_name") == tool_name and tc.get("success")]
        if not successful_calls:
            return False
        if expected_args and not any(_match_args(tc.get("args", {}), expected_args) for tc in successful_calls):
            return False

    return True


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


def _fmt_latency(ms: int | None) -> str:
    if ms is None:
        return _DASH
    return f"{ms / 1000:.1f}s"


def _print_header(use_judge: bool) -> None:
    if use_judge:
        header = f"{'Scenario':<{_W_ID}}  {'Agent':<{_W_AGENT}}  {'Route':6}  {'Tools':6}  {'Outcome':8}  {'Latency':8}  {'Qual':5}  {'Tone':5}  {'T.Use':5}  Pass"
    else:
        header = f"{'Scenario':<{_W_ID}}  {'Agent':<{_W_AGENT}}  {'Route':6}  {'Tools':6}  {'Outcome':8}  {'Latency':8}"
    print(header)
    print("─" * len(header))


def _print_row(
    scenario_id: str,
    agent_used: str | None,
    routing: bool | None,
    tools: bool | None,
    outcome: bool | None,
    latency_ms: int | None,
    judge_score: dict | None,
    error: str | None,
) -> None:
    sid = scenario_id[:_W_ID]
    agent = (agent_used or "?")[:_W_AGENT]
    route_sym = _sym(routing)
    tools_sym = _sym(tools)
    outcome_sym = _sym(outcome)
    lat = _fmt_latency(latency_ms)

    if error:
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {'ERR':6}  {tools_sym:6}  {outcome_sym:8}  {lat:8}  {error[:35]}")
        return

    if judge_score:
        q = _fmt_score(judge_score.get("quality"))
        t = _fmt_score(judge_score.get("tone"))
        tu = _fmt_score(judge_score.get("tool_use"))
        p = _TICK if judge_score.get("pass") else _CROSS
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {route_sym:6}  {tools_sym:6}  {outcome_sym:8}  {lat:8}  {q:5}  {t:5}  {tu:5}  {p}")
    else:
        print(f"{sid:<{_W_ID}}  {agent:<{_W_AGENT}}  {route_sym:6}  {tools_sym:6}  {outcome_sym:8}  {lat:8}")


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

        oc_total = t.get("outcome_correct", 0) + t.get("outcome_wrong", 0)
        if oc_total > 0:
            print(f"  Outcome correct:     {t['outcome_correct']}/{oc_total} ({100*t['outcome_correct']//oc_total}%)")
        if t.get("outcome_unchecked", 0) > 0:
            print(f"  Outcome unchecked:   {t['outcome_unchecked']}")

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

    lats = run.get("totals", {}).get("latency_values", [])
    if lats:
        lats_s = sorted(lats)
        avg_lat = sum(lats_s) / len(lats_s)
        p95_lat = lats_s[int(len(lats_s) * 0.95)]
        print()
        print("  Latency (wall-clock)")
        print(f"    avg: {avg_lat/1000:.1f}s   p95: {p95_lat/1000:.1f}s   max: {lats_s[-1]/1000:.1f}s")

    tok = run.get("totals", {})
    if tok.get("total_tokens", 0) > 0:
        n = tok.get("total", 1)
        print()
        print("  Tokens (from llm_cost_log)")
        print(f"    total: {tok['total_tokens']:,}   avg/scenario: {tok['total_tokens']//n:,}")
        if tok.get("prompt_tokens") and tok.get("completion_tokens"):
            print(f"    prompt: {tok['prompt_tokens']:,}   completion: {tok['completion_tokens']:,}")

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
            oc_c = stats.get("outcome_correct", 0)
            oc_w = stats.get("outcome_wrong", 0)
            oc_total_a = oc_c + oc_w
            rt_str = f"  routing {rt_c}/{rt_total_a}" if rt_total_a > 0 else ""
            tl_str = f"  tools {tl_c}/{tl_total_a}" if tl_total_a > 0 else ""
            oc_str = f"  outcome {oc_c}/{oc_total_a}" if oc_total_a > 0 else ""
            judge_str = f"  passed {passed}/{judged}" if judged > 0 else ""
            q = stats.get("avg_quality")
            q_str = f"  quality {q:.1f}" if q else ""
            avg_lat_a = stats.get("avg_latency_ms")
            lat_str = f"  avg {avg_lat_a/1000:.1f}s" if avg_lat_a else ""
            print(f"    {agent:<14} {stats['total']:3} scenarios{rt_str}{tl_str}{oc_str}{judge_str}{q_str}{lat_str}")


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
        latency_ms: int | None = None

        t_start = time.monotonic()
        try:
            ze_result = await _run_turns(scenario, session_id, ze_url, ze_key)
            error = ze_result.get("error")
        except Exception as exc:
            error = str(exc)
        latency_ms = int((time.monotonic() - t_start) * 1000)

        agent_used = ze_result.get("agent_used") if not error else None

        tools: bool | None = None
        outcome: bool | None = None
        verify_results: list[dict] = []
        scenario_metrics: dict = {}
        if not error:
            routing = _routing_correct(scenario, agent_used)
            tools = _tools_correct(scenario, ze_result)

            if scenario.get("verify"):
                vr = await run_verification(scenario["verify"])
                verify_results = [
                    {"table": r.table, "where": r.where, "expect": r.expect,
                     "actual_count": r.actual_count, "passed": r.passed, "error": r.error}
                    for r in vr
                ]
                outcome = _outcome_correct(vr)

            sm = await fetch_session_metrics(session_id)
            if sm:
                scenario_metrics = {
                    "prompt_tokens": sm.prompt_tokens,
                    "completion_tokens": sm.completion_tokens,
                    "total_tokens": sm.total_tokens,
                    "llm_duration_ms": sm.llm_duration_ms,
                    "llm_calls": sm.llm_calls,
                    "models": sm.models,
                }

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

        _print_row(sid, agent_used, routing, tools, outcome, latency_ms, judge_score if judge_score and "error" not in judge_score else None, error)

        agent_key = agent_used or scenario.get("expected_agent") or "unknown"
        if agent_key not in by_agent:
            by_agent[agent_key] = {
                "total": 0,
                "routing_correct": 0, "routing_wrong": 0,
                "tools_correct": 0, "tools_wrong": 0,
                "outcome_correct": 0, "outcome_wrong": 0,
                "judged": 0, "passed": 0, "quality_sum": 0,
                "latency_sum_ms": 0, "total_tokens": 0,
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
        if outcome is True:
            by_agent[agent_key]["outcome_correct"] += 1
        elif outcome is False:
            by_agent[agent_key]["outcome_wrong"] += 1
        if latency_ms is not None:
            by_agent[agent_key]["latency_sum_ms"] += latency_ms
        by_agent[agent_key]["total_tokens"] += scenario_metrics.get("total_tokens", 0)
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
            "outcome_correct": outcome,
            "verify_results": verify_results,
            "latency_ms": latency_ms,
            "metrics": scenario_metrics,
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
        if stats["total"] > 0 and stats.get("latency_sum_ms", 0) > 0:
            stats["avg_latency_ms"] = stats["latency_sum_ms"] // stats["total"]
        stats.pop("latency_sum_ms", None)

    latency_vals = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
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
            "outcome_correct": sum(1 for r in results if r["outcome_correct"] is True),
            "outcome_wrong": sum(1 for r in results if r["outcome_correct"] is False),
            "outcome_unchecked": sum(1 for r in results if r["outcome_correct"] is None),
            "judged": len(judged_results),
            "passed": sum(1 for r in judged_results if r["judge"].get("pass")),
            "avg_quality": sum(quality_vals) / len(quality_vals) if quality_vals else None,
            "avg_tone": sum(tone_vals) / len(tone_vals) if tone_vals else None,
            "avg_tool_use": sum(tool_vals) / len(tool_vals) if tool_vals else None,
            "latency_values": latency_vals,
            "total_tokens": sum(r.get("metrics", {}).get("total_tokens", 0) for r in results),
            "prompt_tokens": sum(r.get("metrics", {}).get("prompt_tokens", 0) for r in results),
            "completion_tokens": sum(r.get("metrics", {}).get("completion_tokens", 0) for r in results),
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
