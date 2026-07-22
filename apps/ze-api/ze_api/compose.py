from __future__ import annotations

from typing import Any

from ze_agents.settings import Settings as CoreSettings
from ze_automation.bootstrap import register_proactive_jobs as register_automation_jobs
from ze_core.bootstrap import register_engine_jobs
from ze_correlation.bootstrap import (
    register_proactive_jobs as register_correlation_jobs,
)
from ze_memory.bootstrap import (
    consolidation_enabled,
    register_dream_jobs,
    register_memory_jobs,
)
from ze_proactive.bootstrap import register_notification_jobs
from ze_proactive.notification_store import NotificationStore
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler
from ze_worldstate.bootstrap import register_proactive_jobs as register_worldstate_jobs


def register_all_proactive_jobs(
    scheduler: ProactiveScheduler,
    *,
    settings: Any,
    core_settings: CoreSettings,
    automation: Any,
    correlation: Any,
    worldstate: Any = None,
    shared: Any,
    plugins: list,
    notifier: ProactiveNotifier,
    push_log_store: PushLogStore,
    notification_store: NotificationStore | None = None,
    dream_job: Any = None,
    pool: Any = None,
) -> None:
    register_automation_jobs(
        scheduler,
        settings,
        automation,
        notifier=notifier,
        push_log_store=push_log_store,
    )
    if notification_store is not None:
        register_notification_jobs(scheduler, settings, notification_store)
    register_engine_jobs(automation.workflow_scheduler, settings, shared)
    register_memory_jobs(scheduler, settings, shared)
    register_correlation_jobs(
        scheduler,
        settings,
        correlation,
        shared=shared,
        notifier=notifier,
        push_log_store=push_log_store,
    )
    if worldstate is not None:
        register_worldstate_jobs(scheduler, settings, worldstate)
    for plugin in plugins:
        plugin.register_proactive_jobs(
            scheduler,
            core_settings,
            consolidation_enabled=consolidation_enabled(settings),
        )
    if dream_job is not None:
        register_dream_jobs(scheduler, settings, dream_job, pool=pool)
