"""
ze_eval — eval infrastructure for Ze.

Public surface for use by entrypoints and tests:
  - ZeEvalClient: HTTP client for /eval/chat
  - load_scenarios: load YAML scenario definitions
  - load_scenario_by_id: look up a single scenario
"""
from ze_eval.client import ZeEvalClient
from ze_eval.scenario import load_scenario_by_id, load_scenarios

__all__ = ["ZeEvalClient", "load_scenarios", "load_scenario_by_id"]
