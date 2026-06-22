from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ze_agents.logging import get_logger
from ze_correlation import CorrelationEngine, CorrelationJob, CorrelationPushConsumer, PostgresHypothesisStore
from ze_memory.relevance import RelevanceModel
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler

log = get_logger(__name__)


@dataclass
class CorrelationStack:
    hypothesis_store: PostgresHypothesisStore
    correlation_engine: CorrelationEngine


def build_correlation_stack(shared: Any, settings: Any) -> CorrelationStack:
    hypothesis_store = PostgresHypothesisStore(pool=shared.pool)
    relevance_model = RelevanceModel(memory_store=shared.memory_store)
    correlation_engine = CorrelationEngine(
        memory_store=shared.memory_store,
        relevance_model=relevance_model,
        llm_client=shared.openrouter_client,
        hypothesis_store=hypothesis_store,
        settings=settings,
    )
    return CorrelationStack(
        hypothesis_store=hypothesis_store,
        correlation_engine=correlation_engine,
    )


def register_proactive_jobs(
    scheduler: ProactiveScheduler,
    settings: Any,
    stack: CorrelationStack,
    *,
    shared: Any,
    notifier: ProactiveNotifier,
    push_log_store: PushLogStore,
) -> None:
    raw_cfg = getattr(settings, "config", {}) or {}
    _push_cfg = raw_cfg.get("correlation", {}).get("push", {})
    _push_schedule = _push_cfg.get("schedule", "0 */4 * * *")
    push_consumer = CorrelationPushConsumer(
        engine=stack.correlation_engine,
        hypothesis_store=stack.hypothesis_store,
        memory_store=shared.memory_store,
        notifier=notifier,
        push_log=push_log_store,
        settings=settings,
        embedder=shared.embedder,
    )
    correlation_job = CorrelationJob(push_consumer=push_consumer)
    scheduler.add_cron_job(
        fn=correlation_job.run,
        cron=_push_schedule,
        job_id=CorrelationJob.job_id,
    )
    log.info("correlation_push_job_scheduled", cron=_push_schedule)
