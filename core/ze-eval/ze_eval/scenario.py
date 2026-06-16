"""Scenario loading from YAML files."""
from __future__ import annotations

from pathlib import Path

import yaml

# Default: eval/scenarios/ at the repo root (two levels up from this package)
_DEFAULT_SCENARIOS_DIR = Path(__file__).parent.parent.parent.parent / "eval" / "scenarios"


def load_scenarios(
    tag: str = "",
    scenarios_dir: Path | None = None,
) -> list[dict]:
    """Load all scenarios from YAML files, optionally filtered by tag."""
    base = scenarios_dir or _DEFAULT_SCENARIOS_DIR
    scenarios: list[dict] = []
    for path in sorted(base.glob("*.yaml")):
        items = yaml.safe_load(path.read_text()) or []
        for item in items:
            item.setdefault("file", path.stem)
            scenarios.append(item)
    if tag:
        scenarios = [s for s in scenarios if tag in s.get("tags", [])]
    return scenarios


def load_scenario_by_id(
    scenario_id: str,
    scenarios_dir: Path | None = None,
) -> dict | None:
    """Return a single scenario by its id, or None if not found."""
    for scenario in load_scenarios(scenarios_dir=scenarios_dir):
        if scenario.get("id") == scenario_id:
            return scenario
    return None
