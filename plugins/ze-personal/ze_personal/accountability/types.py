from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentCostSummary:
    agent: str
    run_count: int
    total_tokens: int
    cost_usd: float


@dataclass
class ActivitySummary:
    period_days: int
    agent_costs: list[AgentCostSummary]
    goals_advanced: list[str]
    goals_stalled: list[str]
    workflow_failures: list[str]
    anomalies: list[str]
    total_cost_usd: float


@dataclass
class AnomalyRecord:
    agent: str
    run_cost_usd: float
    baseline_cost_usd: float
    multiplier: float
    session_id: str | None
    detected_at: str
