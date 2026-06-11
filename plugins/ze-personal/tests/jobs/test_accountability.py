from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_personal.accountability.summarizer import build_narrative
from ze_personal.accountability.types import (
    ActivitySummary,
    AgentCostSummary,
    AnomalyRecord,
)
from ze_personal.jobs.accountability import AccountabilityJob
from ze_personal.jobs.cost_anomaly import CostAnomalyJob


# ── ActivitySummary / build_narrative ─────────────────────────────────────────

def _empty_summary(period_days: int = 7) -> ActivitySummary:
    return ActivitySummary(
        period_days=period_days,
        agent_costs=[],
        goals_advanced=[],
        goals_stalled=[],
        workflow_failures=[],
        anomalies=[],
        total_cost_usd=0.0,
    )


def test_build_narrative_empty_shows_no_activity():
    result = build_narrative(_empty_summary())
    assert "No activity recorded yet" in result


def test_build_narrative_period_label_7_days():
    result = build_narrative(_empty_summary(period_days=7))
    assert "last 7 days" in result


def test_build_narrative_period_label_24_hours():
    result = build_narrative(_empty_summary(period_days=1))
    assert "last 24 hours" in result


def test_build_narrative_includes_cost():
    summary = ActivitySummary(
        period_days=7,
        agent_costs=[AgentCostSummary("research", 10, 5000, 0.25)],
        goals_advanced=[],
        goals_stalled=[],
        workflow_failures=[],
        anomalies=[],
        total_cost_usd=0.25,
    )
    text = build_narrative(summary)
    assert "0.2500" in text
    assert "research" in text
    assert "10 runs" in text


def test_build_narrative_goals_advanced():
    summary = _empty_summary()
    summary.goals_advanced = ["Send 10 outreach emails"]
    text = build_narrative(summary)
    assert "Send 10 outreach emails" in text
    assert "Advanced" in text


def test_build_narrative_goals_stalled():
    summary = _empty_summary()
    summary.goals_stalled = ["Write technical blog post"]
    text = build_narrative(summary)
    assert "Write technical blog post" in text
    assert "Stalled" in text


def test_build_narrative_workflow_failure():
    summary = _empty_summary()
    summary.workflow_failures = ["email_digest"]
    text = build_narrative(summary)
    assert "email_digest" in text
    assert "Failed" in text


def test_build_narrative_anomaly():
    summary = _empty_summary()
    summary.anomalies = ["prospecting spent $0.31 on one run (5.0× baseline) on 2026-06-09"]
    text = build_narrative(summary)
    assert "prospecting" in text
    assert "Anomalies" in text


def test_build_narrative_no_failures_message():
    summary = _empty_summary()
    text = build_narrative(summary)
    assert "no failures" in text


# ── AccountabilityJob ─────────────────────────────────────────────────────────

def _make_accountability_job(*, dedup_hit: bool = False) -> AccountabilityJob:
    notifier = AsyncMock()
    push_log = AsyncMock()
    push_log.was_sent_within_hours = AsyncMock(return_value=dedup_hit)
    push_log.log = AsyncMock()
    push_log.list_workflow_failures_within_hours = AsyncMock(return_value=[])

    acc_store = AsyncMock()
    acc_store.list_anomalies_since = AsyncMock(return_value=[])

    goal_store = AsyncMock()
    goal_store.list_active = AsyncMock(return_value=[])

    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"total_cost": 0.0})
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=conn)

    job = object.__new__(AccountabilityJob)
    job._notifier = notifier
    job._push_log = push_log
    job._acc_store = acc_store
    job._goal_store = goal_store
    job._pool = pool
    job._stall_days = 3
    return job


async def test_accountability_job_skips_when_dedup_hit():
    job = _make_accountability_job(dedup_hit=True)
    await job.run()
    job._notifier.push.assert_not_called()


async def test_accountability_job_sends_narrative_when_no_dedup():
    job = _make_accountability_job(dedup_hit=False)
    await job.run()
    job._notifier.push.assert_called_once()
    job._push_log.log.assert_called_once()


# ── CostAnomalyJob ────────────────────────────────────────────────────────────

def _make_cost_anomaly_job(
    *,
    baseline_rows: list[dict],
    recent_rows: list[dict],
    existing_anomalies: list = None,
) -> CostAnomalyJob:
    notifier = AsyncMock()

    acc_store = AsyncMock()
    acc_store.clear_older_than = AsyncMock()
    acc_store.list_anomalies_since = AsyncMock(return_value=existing_anomalies or [])
    acc_store.record_anomaly = AsyncMock()

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[baseline_rows, recent_rows])
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=conn)

    job = object.__new__(CostAnomalyJob)
    job._notifier = notifier
    job._acc_store = acc_store
    job._pool = pool
    job._threshold = 4.0
    job._min_samples = 5
    job._retention_days = 30
    return job


def _cost_row(agent: str, cost: float) -> dict:
    return {"agent": agent, "cost_usd": cost}


def _recent_row(agent: str, cost: float, session_id: str = "sess1") -> dict:
    return {"agent": agent, "cost_usd": cost, "session_id": session_id}


async def test_anomaly_job_fires_when_cost_exceeds_threshold():
    # 5 baseline rows at $0.10 each → median = $0.10; a $0.60 run = 6× > 4.0
    baseline = [_cost_row("research", 0.10)] * 5
    recent = [_recent_row("research", 0.60)]
    job = _make_cost_anomaly_job(baseline_rows=baseline, recent_rows=recent)
    await job.run()
    job._acc_store.record_anomaly.assert_called_once()
    job._notifier.push.assert_called_once()
    text = job._notifier.push.call_args[0][0]
    assert "research" in text
    assert "anomaly" in text.lower()


async def test_anomaly_job_no_alert_below_threshold():
    baseline = [_cost_row("research", 0.10)] * 5
    recent = [_recent_row("research", 0.30)]  # 3× < 4.0
    job = _make_cost_anomaly_job(baseline_rows=baseline, recent_rows=recent)
    await job.run()
    job._acc_store.record_anomaly.assert_not_called()
    job._notifier.push.assert_not_called()


async def test_anomaly_job_skips_agents_below_min_samples():
    baseline = [_cost_row("research", 0.10)] * 4  # only 4 samples, min is 5
    recent = [_recent_row("research", 1.00)]
    job = _make_cost_anomaly_job(baseline_rows=baseline, recent_rows=recent)
    await job.run()
    job._acc_store.record_anomaly.assert_not_called()


async def test_anomaly_job_skips_already_alerted_session():
    baseline = [_cost_row("research", 0.10)] * 5
    recent = [_recent_row("research", 0.60, session_id="sess-already")]
    existing = [
        AnomalyRecord(
            agent="research",
            run_cost_usd=0.60,
            baseline_cost_usd=0.10,
            multiplier=6.0,
            session_id="sess-already",
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
    ]
    job = _make_cost_anomaly_job(
        baseline_rows=baseline, recent_rows=recent, existing_anomalies=existing
    )
    await job.run()
    job._acc_store.record_anomaly.assert_not_called()


async def test_anomaly_job_uses_median_not_mean():
    # Baseline: 5×$0.10 + 1×$10.00 → mean is large, median is $0.10
    baseline = [_cost_row("research", 0.10)] * 5 + [_cost_row("research", 10.00)]
    recent = [_recent_row("research", 0.60)]  # 6× the $0.10 median → anomaly
    job = _make_cost_anomaly_job(baseline_rows=baseline, recent_rows=recent)
    await job.run()
    job._acc_store.record_anomaly.assert_called_once()
