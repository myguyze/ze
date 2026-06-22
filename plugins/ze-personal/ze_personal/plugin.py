from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import asyncpg

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_sdk import ZePlugin
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
from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.executor import GoalExecutor
from ze_personal.jobs.briefing import MorningBriefing
from ze_personal.jobs.contacts import ContactReviewNotifier
from ze_personal.jobs.insights import InsightEngine
from ze_personal.onboarding import PersonalOnboardingProvider
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.planner import WorkflowPlanner

log = get_logger(__name__)


class PersonalPlugin(ZePlugin):
    """Domain plugin that wires persona, contacts, and accountability into ze_core graphs."""

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
        workflow_planner: WorkflowPlanner,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
        goal_executor: GoalExecutor,
        suggestion_store: GoalSuggestionStore,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._pool = pool

        self.person_store = PersonStore(pool=pool, memory_store=memory_store)
        self.contact_channel_store = ContactChannelStore(pool=pool)

        # Automation services — owned by ze-api container, injected here
        self.goal_store = goal_store
        self.goal_planner = goal_planner
        self.goal_executor = goal_executor
        self.suggestion_store = suggestion_store
        self.workflow_store = workflow_store
        self.workflow_planner = workflow_planner

        self.contacts_consolidator = ContactsConsolidator(
            pool=pool,
            person_store=self.person_store,
            openrouter_client=openrouter_client,
            settings=settings,
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
        from ze_news.types import GoalTitleProvider

        return {
            PersonStore: self.person_store,
            ContactChannelStore: self.contact_channel_store,
            PostgresGoalStore: self.goal_store,
            GoalTitleProvider: self.goal_store,
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
            "ze_automation.workflow.types",
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
        from ze_automation.graph.routing_context import inject_goal_routing_context
        return inject_goal_routing_context

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_personal.contacts.tools",
            "ze_personal.agents.research.agent",
            "ze_personal.agents.companion.agent",
        ]

    def jobs(self) -> list:
        return [
            self.morning_briefing,
            self.insight_engine,
            self.contact_review,
        ]

    def onboarding(self) -> PersonalOnboardingProvider:
        return PersonalOnboardingProvider()

    async def startup(self, container: Any) -> None:
        # Wire news_store into morning briefing if any plugin provides one.
        for plugin in container.plugins:
            news_store = plugin.configurable_services().get("news_store")
            if news_store is not None:
                self.morning_briefing._news = news_store
                log.info("news_store_wired_to_briefing")
                break

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

