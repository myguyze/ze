from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import asyncpg

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_sdk import ZePlugin
from ze_agents.registry import get_agent
from ze_agents.settings import Settings as CoreSettings
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler
from ze_sdk.memory import PostgresMemoryStore
from ze_personal.contacts.channel_store import ContactChannelStore
from ze_personal.contacts.consolidator import ContactsConsolidator
from ze_personal.contacts.store import PersonStore
from ze_automation.goals.postgres import PostgresGoalStore as GoalStore
from ze_automation.goals.suggestion_store import GoalSuggestionStore
from ze_personal.goals.executor import GoalExecutor
from ze_personal.goals.planner import GoalPlanner
from ze_personal.accountability.store import AccountabilityStore
from ze_personal.jobs.accountability import AccountabilityJob
from ze_personal.jobs.briefing import MorningBriefing
from ze_personal.jobs.contacts import ContactReviewNotifier
from ze_personal.jobs.cost_anomaly import CostAnomalyJob
from ze_personal.jobs.goal_narrative import GoalNarrativeJob
from ze_personal.jobs.goal_suggestion import GoalSuggestionJob
from ze_personal.jobs.insights import InsightEngine
from ze_personal.jobs.stuck_goals import StuckGoalJob
from ze_personal.onboarding import PersonalOnboardingProvider
from ze_automation.workflow.store import WorkflowStore
from ze_personal.workflow.planner import WorkflowPlanner

log = get_logger(__name__)


class PersonalPlugin(ZePlugin):
    """Domain plugin that wires the personal-assistant layer into ze_core graphs.

    Constructs all personal-assistant domain services from shared primitives.
    Graph hooks, proactive jobs, and workflow execution are wired here.
    """

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        openrouter_client: LLMClient,
        settings: CoreSettings,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        memory_store: PostgresMemoryStore,
        workflow_store: WorkflowStore,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._pool = pool

        self.person_store = PersonStore(pool=pool, memory_store=memory_store)
        self.contact_channel_store = ContactChannelStore(pool=pool)
        self.goal_store = GoalStore(pool=pool)
        self.goal_planner = GoalPlanner(
            client=openrouter_client,
            memory_store=memory_store,
        )
        self.workflow_store = workflow_store
        self.workflow_planner = WorkflowPlanner(openrouter_client=openrouter_client)
        self.suggestion_store = GoalSuggestionStore(pool=pool)
        self.contacts_consolidator = ContactsConsolidator(
            pool=pool,
            person_store=self.person_store,
            openrouter_client=openrouter_client,
            settings=settings,
        )
        self.goal_executor = GoalExecutor(
            goal_store=self.goal_store,
            goal_planner=self.goal_planner,
            push=notifier.push_notification,
            agent_getter=get_agent,
            memory_store=memory_store,
        )

        self.morning_briefing = MorningBriefing(
            notifier=notifier,
            push_log_store=push_log_store,
            memory_store=memory_store,
            workflow_store=workflow_store,
            person_store=self.person_store,
            settings=settings,
            news_store=None,
            goal_store=self.goal_store,
        )
        self.insight_engine = InsightEngine(
            notifier=notifier,
            pool=pool,
            openrouter_client=openrouter_client,
            settings=settings,
        )
        self.contact_review = ContactReviewNotifier(
            person_store=self.person_store,
            notifier=notifier,
        )
        self.goal_narrative = GoalNarrativeJob(
            notifier=notifier,
            push_log_store=push_log_store,
            goal_store=self.goal_store,
            goal_planner=self.goal_planner,
        )
        self.goal_suggestion = GoalSuggestionJob(
            notifier=notifier,
            goal_store=self.goal_store,
            suggestion_store=self.suggestion_store,
            planner=self.goal_planner,
            memory_store=memory_store,
        )
        self.stuck_goals = StuckGoalJob(
            notifier=notifier,
            goal_store=self.goal_store,
        )
        accountability_store = AccountabilityStore(pool=pool)
        self.accountability = AccountabilityJob(
            notifier=notifier,
            push_log_store=push_log_store,
            accountability_store=accountability_store,
            goal_store=self.goal_store,
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

    def data_domains(self):
        from ze_sdk import DataDomain
        from ze_api.data.assembler import bulk_insert

        def _export(tbl: str):
            async def _fn(pool) -> list[dict]:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(f"SELECT * FROM {tbl}")
                    return [dict(r) for r in rows]
            return _fn

        def _delete(*tables: str):
            async def _fn(pool) -> None:
                async with pool.acquire() as conn:
                    for tbl in tables:
                        await conn.execute(f"DELETE FROM {tbl}")
            return _fn

        def _import(tbl: str):
            async def _fn(conn, rows: list[dict]) -> int:
                return await bulk_insert(conn, tbl, rows)
            return _fn

        def _domain(name: str, tbl: str, order: int) -> DataDomain:
            return DataDomain(name, _export(tbl), _delete(tbl), delete_order=order, importer=_import(tbl))

        return [
            # Memory (leaf, no FK dependencies) — order 10
            _domain("memory.facts", "user_facts", 10),
            _domain("memory.episodes", "episodes", 10),
            _domain("memory.profile", "user_profile", 10),
            _domain("memory.profile_facets", "memory_profile_facets", 10),
            _domain("memory.entities", "memory_entities", 10),
            _domain("memory.events", "memory_events", 10),
            _domain("memory.procedures", "memory_procedures", 10),
            _domain("memory.relationships", "memory_relationships", 10),
            _domain("memory.task_state", "memory_task_state", 10),
            _domain("memory.insights", "insights", 10),
            _domain("persona.state", "persona_state", 10),
            # Contact children (FK to contacts) — order 20
            _domain("contacts.channels", "contact_channels", 20),
            _domain("contacts.sources", "contact_sources", 20),
            _domain("contacts.relationships", "contact_relationships", 20),
            # Goal children (FK to goals) — order 20
            _domain("goals.milestones", "goal_milestones", 20),
            _domain("goals.gates", "goal_gates", 20),
            _domain("goals.learnings", "goal_learnings", 20),
            _domain("goals.traces", "goal_execution_traces", 20),
            _domain("goals.suggestions", "goal_suggestions", 20),
            # Workflow children (FK to workflows) — order 20
            _domain("workflow.executions", "workflow_executions", 20),
            # Parents — order 30
            _domain("contacts.persons", "contacts", 30),
            _domain("goals.goals", "goals", 30),
            _domain("workflow.workflows", "workflows", 30),
        ]

    def agent_deps(self, accumulated: dict) -> dict:
        from ze_personal.contacts.store import PersonStore
        from ze_personal.contacts.channel_store import ContactChannelStore
        from ze_automation.goals.postgres import PostgresGoalStore
        from ze_personal.goals.planner import GoalPlanner
        from ze_personal.goals.executor import GoalExecutor
        from ze_personal.workflow.planner import WorkflowPlanner
        from ze_news.types import GoalTitleProvider

        return {
            PersonStore: self.person_store,
            ContactChannelStore: self.contact_channel_store,
            PostgresGoalStore: self.goal_store,
            GoalTitleProvider: self.goal_store,
            GoalPlanner: self.goal_planner,
            GoalExecutor: self.goal_executor,
            WorkflowPlanner: self.workflow_planner,
        }

    def rest_stores(self) -> dict[str, Any]:
        return {
            "goal_store": self.goal_store,
            "person_store": self.person_store,
        }

    def configurable_services(self) -> dict[str, Any]:
        from ze_personal.persona.identity import build_identity_block
        from ze_personal.graph.memory_hooks import contact_proposal_hook
        return {
            "identity_builder": build_identity_block,
            "memory_hooks": [contact_proposal_hook],
            "person_store": self.person_store,
            "goal_store": self.goal_store,
            "contact_channel_store": self.contact_channel_store,
            "workflow_planner": self.workflow_planner,
        }

    def state_extensions(self) -> type | None:
        from ze_personal.graph.workflow import WorkflowAgentState
        return WorkflowAgentState

    def checkpoint_serde_modules(self) -> tuple[str, ...]:
        return (
            "ze_personal.workflow.types",
            "ze_personal.contacts.types",
        )

    def memory_policies(self) -> dict[str, Any]:
        from ze_memory.policies import (
            CompanionPolicy,
            GoalsPolicy,
            PlannerPolicy,
            ResearchPolicy,
            WorkflowPolicy,
        )

        return {
            "companion": CompanionPolicy(),
            "research": ResearchPolicy(),
            "goals": GoalsPolicy(),
            "workflow": WorkflowPolicy(),
            "planner": PlannerPolicy(),
        }

    def pre_route_node(self) -> Callable | None:
        from ze_personal.graph.routing_context import inject_goal_routing_context
        return inject_goal_routing_context

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_personal.contacts.tools",
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

    def onboarding(self) -> PersonalOnboardingProvider:
        return PersonalOnboardingProvider()

    async def startup(self, container: Any) -> None:
        api_settings = container.settings

        # Wire news_store into morning briefing if any plugin provides one.
        for plugin in container.plugins:
            news_store = plugin.configurable_services().get("news_store")
            if news_store is not None:
                self.morning_briefing._news = news_store
                log.info("news_store_wired_to_briefing")
                break

        # Build workflow graph and configure executor on the shared scheduler.
        from ze_personal.graph.workflow import build_workflow_graph

        workflow_graph = build_workflow_graph(
            checkpointer=container._checkpointer,
            plugins=container.plugins,
        )

        workflow_graph_config: dict = {
            "configurable": {
                "capability_gate": container.capability_gate,
                "memory_store": container.memory_store,
                "persona_store": container.persona_store,
                "openrouter_client": container.openrouter_client,
                "embedder": container.embedder,
                "settings": api_settings,
                "workflow_store": self.workflow_store,
                "workflow_planner": self.workflow_planner,
                "router": container.router,
            }
        }

        async def _workflow_executor(workflow: Any, execution_id: Any) -> None:
            from ze_agents.interface.types import RawInput
            from ze_core.conversation import make_graph_input
            from ze_core.telemetry.context import set_flow_context
            set_flow_context("workflow_execution", session_id=f"workflow:{workflow.id}")
            initial_state = {
                **make_graph_input(
                    RawInput(text=f"[workflow] {workflow.name}"),
                    f"workflow:{workflow.id}",
                ),
                "workflow_id": workflow.id,
                "workflow_execution_id": execution_id,
                "workflow_steps": workflow.steps,
                "current_step_index": 0,
                "workflow_step_results": [],
            }
            run_config = {
                **workflow_graph_config,
                "configurable": {
                    **workflow_graph_config.get("configurable", {}),
                    "thread_id": str(execution_id),
                    "workflow_store": self.workflow_store,
                },
            }
            await workflow_graph.ainvoke(initial_state, run_config)

        async def _workflow_failure_handler(workflow: Any, exc: Exception) -> None:
            alerts_cfg = api_settings.proactive_config.get("alerts", {})
            if not alerts_cfg.get("workflow_failure_enabled", True):
                return
            cooldown = int(alerts_cfg.get("workflow_failure_cooldown_hours", 1))
            event_type = f"workflow_failure:{workflow.id}"
            push_log = getattr(container, "_push_log_store", None)
            if push_log and await push_log.was_sent_within_hours(event_type, cooldown):
                log.info("failure_alert_suppressed_cooldown", workflow=workflow.name)
                return
            await self._notifier.push(
                f"Workflow failed: *{workflow.name}*\n`{str(exc)[:200]}`",
                format="markdown",
                urgency="high",
            )
            if push_log:
                await push_log.log(event_type, workflow.name)
            log.info("failure_alert_sent", workflow=workflow.name)

        container.workflow_scheduler.configure_executor(
            executor=_workflow_executor,
            on_failure=_workflow_failure_handler,
        )

        # Register goal advance sweep on the proactive scheduler.
        async def _sweep_active_goals() -> None:
            goals = await self.goal_store.list_for_advance()
            for g in goals:
                asyncio.create_task(self.goal_executor.advance(g.id))

        container.proactive_scheduler.add_cron_job(
            fn=_sweep_active_goals,
            cron="*/15 * * * *",
            job_id="goal_advance_sweep",
        )
        log.info("goal_advance_sweep_scheduled")

        # Register contacts consolidation cron job.
        if container.settings.consolidation_enabled:
            contacts_cfg = self._settings.config.get("contacts", {})
            contacts_cron = contacts_cfg.get("consolidation", {}).get("nightly_cron", "0 3 * * *")
            container.proactive_scheduler.add_cron_job(
                fn=self.contacts_consolidator.run,
                cron=contacts_cron,
                job_id="contacts_consolidation",
            )
            log.info("contacts_consolidation_scheduled", cron=contacts_cron)

    @property
    def goal_suggestion_store(self) -> GoalSuggestionStore:
        return self.suggestion_store

    def register_proactive_jobs(
        self,
        scheduler: ProactiveScheduler,
        settings: CoreSettings,
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

            anomaly_threshold = float(acc_cfg.get("anomaly_threshold", 4.0))
            min_samples = int(acc_cfg.get("anomaly_min_samples", 5))
            retention_days = int(acc_cfg.get("anomaly_retention_days", 30))
            self.cost_anomaly._threshold = anomaly_threshold
            self.cost_anomaly._min_samples = min_samples
            self.cost_anomaly._retention_days = retention_days
            stall_days = int(acc_cfg.get("stall_days", 3))
            self.accountability._stall_days = stall_days

            scheduler.register(
                self.cost_anomaly,
                cron=acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"),
            )
            log.info("cost_anomaly_scheduled", cron=acc_cfg.get("cost_anomaly_schedule", "0 */6 * * *"))
