"""
Objective scoring functions for eval scenarios.

These are deterministic checks — no LLM calls. Each returns True/False/None
where None means the scenario did not declare that expectation.
"""
from __future__ import annotations

from ze_eval.types import VerifyResult


def routing_correct(scenario: dict, agent_used: str | None) -> bool | None:
    expected = scenario.get("expected_agent")
    if not expected or not agent_used:
        return None
    return agent_used == expected


def tools_correct(scenario: dict, ze_result: dict) -> bool | None:
    """
    Check that every tool listed in expected_tools was called and succeeded.

    Each entry may be a bare string (name only) or a dict with 'name' and
    optional 'args' conditions. Returns None when the scenario declares no
    expected_tools.
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


def outcome_correct(verify_results: list[VerifyResult]) -> bool | None:
    """True only if every DB verification check passed."""
    if not verify_results:
        return None
    return all(r.passed for r in verify_results)


def _collect_tool_calls(ze_result: dict) -> list[dict]:
    turns = ze_result.get("turns")
    if turns:
        calls: list[dict] = []
        for turn in turns:
            calls.extend(turn["result"].get("tool_calls", []))
        return calls
    return ze_result.get("tool_calls", [])


def _match_args(actual: dict, expected_args: dict) -> bool:
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
