from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import asyncpg

from ze_core.logging import get_logger
from ze_core.plugin import ZePlugin
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.push_log_store import PushLogStore
from ze_core.proactive.scheduler import ProactiveScheduler
from ze_core.settings import Settings
from ze_core.openrouter.client import OpenRouterClient
from ze_memory.retriever import PostgresMemoryStore
from ze_personal.contacts.store import PersonStore
from ze_personal.goals.planner import GoalPlanner
from ze_personal.goals.postgres import PostgresGoalStore as GoalStore
from ze_personal.goals.suggestion_store import GoalSuggestionStore
from ze_personal.accountability.store import AccountabilityStore
from ze_personal.jobs.accountability import AccountabilityJob
from ze_personal.jobs.briefing import MorningBriefing
from ze_personal.jobs.contacts import ContactReviewNotifier
from ze_personal.jobs.cost_anomaly import CostAnomalyJob
from ze_personal.jobs.goal_narrative import GoalNarrativeJob
from ze_personal.jobs.goal_suggestion import GoalSuggestionJob
from ze_personal.jobs.insights import InsightEngine
from ze_personal.jobs.stuck_goals import StuckGoalJob
from ze_personal.workflow.store import WorkflowStore

if TYPE_CHECKING:
    from ze_memory.store import MemoryStore

log = get_logger(__name__)


class PersonalPlugin(ZePlugin):
    """Domain plugin that wires the personal-assistant layer into ze_core graphs.

    Contributes:
    - identity_builder: builds the persona/memory context block injected into agent
      system prompts (via AgentContext.extensions).
    - memory_hooks: post-write callables; currently runs contact proposal extraction
      after every memory write.
    - inject_goal_routing_context: pre-route node that enriches routing state with
      active goal context so goal-related messages route correctly.
    - research + companion agents and proactive jobs (briefing, insights, goals, contacts).
    """

    def __init__(
        self,
        *,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        memory_store: PostgresMemoryStore,
        workflow_store: WorkflowStore,
        person_store: PersonStore,
        settings: Settings,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
        suggestion_store: GoalSuggestionStore,
        openrouter_client: OpenRouterClient,
        pool: asyncpg.Pool,
        news_store: Any | None = None,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._push_log_store = push_log_store
        self._memory_store = memory_store
        self._workflow_store = workflow_store
        self._person_store = person_store
        self._goal_store = goal_store
        self._goal_planner = goal_planner
        self._suggestion_store = suggestion_store
        self._openrouter_client = openrouter_client
        self._pool = pool
        self._news_store = news_store

        self.morning_briefing = MorningBriefing(
            notifier=notifier,
            push_log_store=push_log_store,
            memory_store=memory_store,
            workflow_store=workflow_store,
            person_store=person_store,
            settings=settings,
            news_store=news_store,
            goal_store=goal_store,
        )
        self.insight_engine = InsightEngine(
            notifier=notifier,
            pool=pool,
            openrouter_client=openrouter_client,
            settings=settings,
        )
        self.contact_review = ContactReviewNotifier(
            person_store=person_store,
            notifier=notifier,
        )
        self.goal_narrative = GoalNarrativeJob(
            notifier=notifier,
            push_log_store=push_log_store,
            goal_store=goal_store,
            goal_planner=goal_planner,
        )
        self.goal_suggestion = GoalSuggestionJob(
            notifier=notifier,
            goal_store=goal_store,
            suggestion_store=suggestion_store,
            planner=goal_planner,
            memory_store=memory_store,
        )
        self.stuck_goals = StuckGoalJob(
            notifier=notifier,
            goal_store=goal_store,
        )
        accountability_store = AccountabilityStore(pool=pool)
        self.accountability = AccountabilityJob(
            notifier=notifier,
            push_log_store=push_log_store,
            accountability_store=accountability_store,
            goal_store=goal_store,
            pool=pool,
        )
        self.cost_anomaly = CostAnomalyJob(
            notifier=notifier,
            accountability_store=accountability_store,
            pool=pool,
        )

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    def configurable_services(self) -> dict[str, Any]:
        from ze_personal.persona.identity import build_identity_block
        from ze_personal.graph.memory_hooks import contact_proposal_hook
        return {
            "identity_builder": build_identity_block,
            "memory_hooks": [contact_proposal_hook],
        }

    def pre_route_node(self) -> Callable | None:
        from ze_personal.graph.routing_context import inject_goal_routing_context
        return inject_goal_routing_context

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_personal.agents.goals.agent",
            "ze_personal.agents.workflow.agent",
            "ze_personal.agents.research.agent",
            "ze_personal.agents.companion.agent",
        ]

    def jobs(self) -> list:
        return [
            self.morning_briefing,
            self.insight_engine,
            self.contact_review,
            self.goal_narrative,
            self.goal_suggestion,
            self.stuck_goals,
            self.accountability,
            self.cost_anomaly,
        ]

    @property
    def goal_suggestion_store(self) -> GoalSuggestionStore:
        return self._suggestion_store

    def register_proactive_jobs(
        self,
        scheduler: ProactiveScheduler,
        settings: Settings,
        *,
        consolidation_enabled: bool = True,
    ) -> None:
        proactive_cfg = settings.config.get("proactive", {})
        contacts_cfg = settings.config.get("contacts", {})

        briefing_cfg = proactive_cfg.get("briefing", {})
        if briefing_cfg.get("enabled", True):
            scheduler.register(
                self.morning_briefing,
                cron=briefing_cfg.get("cron", "0 8 * * *"),
            )
            log.info("briefing_scheduled", cron=briefing_cfg.get("cron", "0 8 * * *"))

        insights_cfg = proactive_cfg.get("insights", {})
        if insights_cfg.get("enabled", True):
            scheduler.register(
                self.insight_engine,
                cron=insights_cfg.get("cron", "0 7 * * 0"),
            )
            log.info("insights_scheduled")

        if consolidation_enabled:
            review_cron = contacts_cfg.get("consolidation", {}).get("review_cron", "30 8 * * *")
            scheduler.register(self.contact_review, cron=review_cron)
            log.info("contact_review_scheduled", cron=review_cron)

        goal_narrative_cfg = proactive_cfg.get("goal_narrative", {})
        if goal_narrative_cfg.get("enabled", True):
            scheduler.register(
                self.goal_narrative,
                cron=goal_narrative_cfg.get("cron", "0 18 * * 0"),
            )
            log.info("goal_narrative_scheduled", cron=goal_narrative_cfg.get("cron", "0 18 * * 0"))

        goal_suggestion_cfg = proactive_cfg.get("goal_suggestion", {})
        if goal_suggestion_cfg.get("enabled", True):
            scheduler.register(
                self.goal_suggestion,
                cron=goal_suggestion_cfg.get("cron", "0 19 * * 0"),
            )
            log.info("goal_suggestion_scheduled", cron=goal_suggestion_cfg.get("cron", "0 19 * * 0"))

        stuck_goals_cfg = proactive_cfg.get("stuck_goals", {})
        if stuck_goals_cfg.get("enabled", True):
            scheduler.register(
                self.stuck_goals,
                cron=stuck_goals_cfg.get("cron", "0 9 * * 2"),
            )
            log.info("stuck_goals_scheduled", cron=stuck_goals_cfg.get("cron", "0 9 * * 2"))

        acc_cfg = proactive_cfg.get("accountability", {})
        if acc_cfg.get("enabled", True):
            scheduler.register(
                self.accountability,
                cron=acc_cfg.get("schedule", "0 9 * * 1"),
            )
            log.info("accountability_scheduled", cron=acc_cfg.get("schedule", "0 9 * * 1"))

            # Update cost anomaly thresholds from config before registering.
            anomaly_threshold = float(acc_cfg.get("anomaly_threshold", 4.0))
            min_samples = int(acc_cfg.get("anomaly_min_samples", 5))
            retention_days = int(acc_cfg.get("anomaly_retention_days", 30))
            self.cost_anomaly._threshold = anomaly_threshold
            self.cost_anomaly._min_samples = min_samples
            self.cost_anomaly._retention_days = retention_days
            # Update stall_days on accountability job.
            stall_days = int(acc_cfg.get("stall_days", 3))
            self.accountability._stall_days = stall_days

            scheduler.register(
                self.cost_anomaly,
                cron=acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"),
            )
            log.info("cost_anomaly_scheduled", cron=acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"))
