"""
Ze Eval Report — view and compare eval run results.

Usage (via subcommand):
  python eval/run.py report                  # show last run summary
  python eval/run.py report --compare        # diff last two runs
  python eval/run.py report path/to/run.json # show a specific run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_DEFAULT_RESULTS_DIR = Path(__file__).parent.parent.parent.parent / "eval" / "results"


def _load_run(path: Path) -> dict:
    return json.loads(path.read_text())


def _latest_runs(results_dir: Path, n: int = 2) -> list[Path]:
    runs = sorted(results_dir.glob("*.json"), reverse=True)
    return runs[:n]


# ── Summary ───────────────────────────────────────────────────────────────────


def print_summary(run: dict) -> None:
    t = run["totals"]
    ts = run.get("timestamp", run.get("run_id", "?"))[:19].replace("T", " ")

    print(f"Ze Eval — {ts} UTC  (run_id: {run['run_id']})")
    print(f"Ze: {run['ze_url']}   tag: {run['tag'] or 'all'}")
    if run.get("judge_model"):
        print(f"Judge: {run['judge_model']}")
    print()

    rt_total = t["routing_correct"] + t["routing_wrong"]
    rt_pct = f"{100 * t['routing_correct'] // rt_total}%" if rt_total > 0 else "n/a"
    tl_total = t.get("tools_correct", 0) + t.get("tools_wrong", 0)
    tl_pct = f"{100 * t['tools_correct'] // tl_total}%" if tl_total > 0 else "n/a"

    print(f"  Scenarios:           {t['total']}")
    print(f"  Errors:              {t['errors']}")
    print(f"  Routing accuracy:    {t['routing_correct']}/{rt_total} ({rt_pct})")
    print(f"  Routing unchecked:   {t['routing_unchecked']}")
    if tl_total > 0:
        print(f"  Tool call accuracy:  {t['tools_correct']}/{tl_total} ({tl_pct})")
    if t.get("tools_unchecked", 0) > 0:
        print(f"  Tools unchecked:     {t['tools_unchecked']}")
    oc_total = t.get("outcome_correct", 0) + t.get("outcome_wrong", 0)
    oc_pct = f"{100 * t['outcome_correct'] // oc_total}%" if oc_total > 0 else "n/a"
    if oc_total > 0:
        print(f"  Outcome accuracy:    {t['outcome_correct']}/{oc_total} ({oc_pct})")
    if t.get("outcome_unchecked", 0) > 0:
        print(f"  Outcome unchecked:   {t['outcome_unchecked']}")

    if t.get("judged", 0) > 0:
        print()
        print(f"  Judged:              {t['judged']}")
        print(f"  Passed:              {t['passed']}/{t['judged']}")
        if t.get("avg_quality"):
            print(f"  Avg quality:         {t['avg_quality']:.2f}/5")
        if t.get("avg_tone"):
            print(f"  Avg tone:            {t['avg_tone']:.2f}/5")
        if t.get("avg_tool_use"):
            print(f"  Avg tool use:        {t['avg_tool_use']:.2f}/5")

    lats = t.get("latency_values", [])
    if lats:
        lats_s = sorted(lats)
        avg_lat = sum(lats_s) / len(lats_s)
        p95_lat = lats_s[int(len(lats_s) * 0.95)]
        print()
        print("  Latency (wall-clock)")
        print(
            f"    avg: {avg_lat / 1000:.1f}s   p95: {p95_lat / 1000:.1f}s   max: {lats_s[-1] / 1000:.1f}s"
        )

    if t.get("total_tokens", 0) > 0:
        n = t.get("total", 1)
        print()
        print("  Tokens (from llm_cost_log)")
        print(
            f"    total: {t['total_tokens']:,}   avg/scenario: {t['total_tokens'] // n:,}"
        )
        if t.get("prompt_tokens") and t.get("completion_tokens"):
            print(
                f"    prompt: {t['prompt_tokens']:,}   completion: {t['completion_tokens']:,}"
            )

    by_agent = run.get("by_agent", {})
    if by_agent:
        print()
        print("  By agent:")
        for agent, stats in sorted(by_agent.items()):
            rt_c = stats.get("routing_correct", 0)
            rt_w = stats.get("routing_wrong", 0)
            rt_t = rt_c + rt_w
            tl_c = stats.get("tools_correct", 0)
            tl_w = stats.get("tools_wrong", 0)
            tl_t = tl_c + tl_w
            oc_c = stats.get("outcome_correct", 0)
            oc_w = stats.get("outcome_wrong", 0)
            oc_t = oc_c + oc_w
            rt_str = f"  route {rt_c}/{rt_t}" if rt_t > 0 else ""
            tl_str = f"  tools {tl_c}/{tl_t}" if tl_t > 0 else ""
            oc_str = f"  outcome {oc_c}/{oc_t}" if oc_t > 0 else ""
            judged = stats.get("judged", 0)
            passed = stats.get("passed", 0)
            judge_str = f"  passed {passed}/{judged}" if judged > 0 else ""
            q = stats.get("avg_quality")
            q_str = f"  quality {q:.1f}" if q else ""
            avg_lat_a = stats.get("avg_latency_ms")
            lat_str = f"  avg {avg_lat_a / 1000:.1f}s" if avg_lat_a else ""
            print(
                f"    {agent:<16} {stats['total']:3}{rt_str}{tl_str}{oc_str}{judge_str}{q_str}{lat_str}"
            )

    failures = [
        r
        for r in run.get("results", [])
        if r.get("routing_correct") is False
        or (r.get("judge") and not r["judge"].get("pass") and "error" not in r["judge"])
    ]
    if failures:
        print()
        print("  Failures:")
        for r in failures:
            sid = r["scenario_id"]
            why_parts = []
            if r.get("routing_correct") is False:
                why_parts.append(
                    f"routed to {r.get('agent_used')} (expected {r['scenario'].get('expected_agent')})"
                )
            if (
                r.get("judge")
                and not r["judge"].get("pass")
                and "error" not in r["judge"]
            ):
                why_parts.append(r["judge"].get("reasoning", "judge failed")[:80])
            print(f"    {sid}: {' | '.join(why_parts)}")


# ── Diff ──────────────────────────────────────────────────────────────────────


def _delta(old: float | None, new: float | None) -> str:
    if old is None or new is None:
        return ""
    diff = new - old
    if abs(diff) < 0.01:
        return ""
    sign = "+" if diff > 0 else ""
    return f" ({sign}{diff:.2f})"


def print_diff(old: dict, new: dict) -> None:
    old_ts = old.get("timestamp", old.get("run_id", "?"))[:19].replace("T", " ")
    new_ts = new.get("timestamp", new.get("run_id", "?"))[:19].replace("T", " ")
    print("Comparing runs:")
    print(f"  Old: {old_ts} UTC  (run_id: {old['run_id']})")
    print(f"  New: {new_ts} UTC  (run_id: {new['run_id']})")
    print()

    ot, nt = old["totals"], new["totals"]
    ort_t = ot["routing_correct"] + ot["routing_wrong"]
    nrt_t = nt["routing_correct"] + nt["routing_wrong"]
    old_rt_pct = ot["routing_correct"] / ort_t if ort_t > 0 else None
    new_rt_pct = nt["routing_correct"] / nrt_t if nrt_t > 0 else None

    def pct_delta(old_r: float | None, new_r: float | None) -> str:
        if old_r is None or new_r is None:
            return ""
        diff = (new_r - old_r) * 100
        if abs(diff) < 0.5:
            return ""
        sign = "+" if diff > 0 else ""
        return f" ({sign}{diff:.0f}pp)"

    print(
        f"  Routing accuracy:   {ot['routing_correct']}/{ort_t} → {nt['routing_correct']}/{nrt_t}{pct_delta(old_rt_pct, new_rt_pct)}"
    )
    print(f"  Errors:             {ot['errors']} → {nt['errors']}")

    ot_tl = ot.get("tools_correct", 0)
    nt_tl = nt.get("tools_correct", 0)
    ot_tl_t = ot_tl + ot.get("tools_wrong", 0)
    nt_tl_t = nt_tl + nt.get("tools_wrong", 0)
    if nt_tl_t > 0 or ot_tl_t > 0:
        old_tl_pct = ot_tl / ot_tl_t if ot_tl_t > 0 else None
        new_tl_pct = nt_tl / nt_tl_t if nt_tl_t > 0 else None
        print(
            f"  Tool call accuracy: {ot_tl}/{ot_tl_t} → {nt_tl}/{nt_tl_t}{pct_delta(old_tl_pct, new_tl_pct)}"
        )

    ot_oc = ot.get("outcome_correct", 0)
    nt_oc = nt.get("outcome_correct", 0)
    ot_oc_t = ot_oc + ot.get("outcome_wrong", 0)
    nt_oc_t = nt_oc + nt.get("outcome_wrong", 0)
    if nt_oc_t > 0 or ot_oc_t > 0:
        old_oc_pct = ot_oc / ot_oc_t if ot_oc_t > 0 else None
        new_oc_pct = nt_oc / nt_oc_t if nt_oc_t > 0 else None
        print(
            f"  Outcome accuracy:   {ot_oc}/{ot_oc_t} → {nt_oc}/{nt_oc_t}{pct_delta(old_oc_pct, new_oc_pct)}"
        )

    if nt.get("judged", 0) > 0 or ot.get("judged", 0) > 0:
        print(
            f"  Passed:             {ot.get('passed', '-')}/{ot.get('judged', '-')} → {nt.get('passed', '-')}/{nt.get('judged', '-')}"
        )
        print(
            f"  Avg quality:        {ot.get('avg_quality') or '-'} → {nt.get('avg_quality') or '-'}{_delta(ot.get('avg_quality'), nt.get('avg_quality'))}"
        )
        print(
            f"  Avg tone:           {ot.get('avg_tone') or '-'} → {nt.get('avg_tone') or '-'}{_delta(ot.get('avg_tone'), nt.get('avg_tone'))}"
        )

    def _avg_latency(t: dict) -> float | None:
        lats = t.get("latency_values", [])
        return sum(lats) / len(lats) if lats else None

    old_avg_lat = _avg_latency(ot)
    new_avg_lat = _avg_latency(nt)
    if old_avg_lat is not None or new_avg_lat is not None:

        def _fmt_lat(v: float | None) -> str:
            return f"{v / 1000:.1f}s" if v is not None else "-"

        lat_delta = ""
        if old_avg_lat is not None and new_avg_lat is not None:
            diff = (new_avg_lat - old_avg_lat) / 1000
            if abs(diff) >= 0.1:
                sign = "+" if diff > 0 else ""
                lat_delta = f" ({sign}{diff:.1f}s)"
        print(
            f"  Avg latency:        {_fmt_lat(old_avg_lat)} → {_fmt_lat(new_avg_lat)}{lat_delta}"
        )

    if ot.get("total_tokens", 0) > 0 or nt.get("total_tokens", 0) > 0:
        old_tok = ot.get("total_tokens", 0)
        new_tok = nt.get("total_tokens", 0)
        tok_delta = ""
        if old_tok and new_tok:
            diff = new_tok - old_tok
            sign = "+" if diff > 0 else ""
            tok_delta = f" ({sign}{diff:,})"
        print(f"  Total tokens:       {old_tok:,} → {new_tok:,}{tok_delta}")

    old_by_id = {r["scenario_id"]: r for r in old.get("results", [])}
    new_by_id = {r["scenario_id"]: r for r in new.get("results", [])}

    regressions = []
    improvements = []

    for sid, nr in new_by_id.items():
        or_ = old_by_id.get(sid)
        if not or_:
            continue

        old_pass = (
            or_.get("routing_correct") is not False
            and or_.get("tools_correct") is not False
            and or_.get("outcome_correct") is not False
            and (not or_.get("judge") or or_["judge"].get("pass", True))
        )
        new_pass = (
            nr.get("routing_correct") is not False
            and nr.get("tools_correct") is not False
            and nr.get("outcome_correct") is not False
            and (not nr.get("judge") or nr["judge"].get("pass", True))
        )

        if old_pass and not new_pass:
            regressions.append(sid)
        elif not old_pass and new_pass:
            improvements.append(sid)

    if regressions:
        print()
        print(f"  Regressions ({len(regressions)}):")
        for sid in regressions:
            print(f"    - {sid}")

    if improvements:
        print()
        print(f"  Improvements ({len(improvements)}):")
        for sid in improvements:
            print(f"    + {sid}")

    if not regressions and not improvements:
        print()
        print("  No per-scenario changes detected.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(results_dir: Path | None = None) -> None:
    p = argparse.ArgumentParser(description="Ze eval report")
    p.add_argument("run", nargs="?", help="Path to a specific run JSON file")
    p.add_argument("--compare", action="store_true", help="Diff last two runs")
    args = p.parse_args()

    out_dir = results_dir or _DEFAULT_RESULTS_DIR

    if not out_dir.exists() or not list(out_dir.glob("*.json")):
        print("No eval results found. Run 'make eval' first.", file=sys.stderr)
        sys.exit(1)

    if args.compare:
        runs = _latest_runs(out_dir, 2)
        if len(runs) < 2:
            print("Need at least two runs to compare.", file=sys.stderr)
            sys.exit(1)
        old, new = _load_run(runs[1]), _load_run(runs[0])
        print_diff(old, new)
    elif args.run:
        run = _load_run(Path(args.run))
        print_summary(run)
    else:
        runs = _latest_runs(out_dir, 1)
        if not runs:
            print("No eval results found.", file=sys.stderr)
            sys.exit(1)
        print_summary(_load_run(runs[0]))
