from __future__ import annotations

from ze_personal.contacts.store import PersonStore
from ze_core.logging import get_logger
from ze_core.proactive.push_log_store import PushLogStore
from ze_core.settings import Settings
from ze_personal.workflow.store import WorkflowStore
from ze_memory.retriever import PostgresMemoryStore
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.telemetry.context import set_flow_context

_EXCLUSION_KEYS = ("not interested", "don't like", "avoid", "no ")


@proactive_job
class MorningBriefing:
    job_id = "morning_briefing"
    def __init__(
        self,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        memory_store: PostgresMemoryStore,
        workflow_store: WorkflowStore,
        person_store: PersonStore,
        settings: Settings,
        news_store=None,
        goal_store=None,
    ) -> None:
        self._notifier = notifier
        self._push_log = push_log_store
        self._memory = memory_store
        self._workflows = workflow_store
        self._persons = person_store
        self._settings = settings
        self._news = news_store
        self._goal_store = goal_store
        self._log = get_logger(__name__)
        follow_up_cfg = self._settings.config.get("contacts", {}).get("follow_up", {})
        self._stale_days = int(follow_up_cfg.get("stale_days", 7))
        self._max_nudges = int(follow_up_cfg.get("max_nudges", 3))
        news_cfg = settings.config.get("news", {})
        news_personalization_cfg = news_cfg.get("personalization", {})
        self._briefing_news_limit = int(news_personalization_cfg.get("briefing_limit", news_cfg.get("briefing_limit", 8)))
        self._explore_ratio = float(news_personalization_cfg.get("explore_ratio", 0.2))
        self._personalization_enabled = news_personalization_cfg.get("enabled", True)
        self._min_facts = int(news_personalization_cfg.get("min_facts", 5))
        news_credibility_cfg = news_cfg.get("credibility", {})
        self._credibility_flag_in_briefing = news_credibility_cfg.get("flag_in_briefing", True)
        self._credibility_briefing_summary = news_credibility_cfg.get("briefing_summary", True)

    async def run(self) -> None:
        set_flow_context("morning_briefing")

        if await self._push_log.was_sent_within_hours("morning_brief", 20):
            self._log.info("briefing_skipped_dedup")
            return

        unreviewed = await self._memory.count_unreviewed_facts()
        workflows = await self._workflows.list_enabled_scheduled()
        failures = await self._push_log.list_workflow_failures_within_hours(24)
        stale_contacts = await self._persons.list_stale_for_follow_up(
            self._stale_days, self._max_nudges
        )

        threshold = int(
            self._settings.config.get("proactive", {}).get("briefing", {}).get("unreviewed_nudge_threshold", 5)
        )

        lines = ["Good morning! Here's your Ze briefing.", ""]
        lines.append(f"📋 Unreviewed facts: {unreviewed}")

        if workflows:
            names = ", ".join(w.name for w in workflows)
            lines.append(f"⚙️  Scheduled workflows: {names}")
        else:
            lines.append("⚙️  Scheduled workflows: none")

        if failures:
            lines.append("")
            for entry in failures:
                name = entry.payload or "unknown"
                when = entry.sent_at.strftime("%H:%M UTC")
                lines.append(f"⚠️  Recent failure: {name} at {when}")

        if unreviewed >= threshold:
            lines.append("")
            lines.append(f"💡 You have {unreviewed} facts waiting for review.")

        if stale_contacts:
            lines.append("")
            lines.append("📌 Follow-up nudges:")
            for nudge in stale_contacts:
                days = nudge.days_ago
                lines.append(
                    f"  • {nudge.name} — last mentioned {days} day{'s' if days != 1 else ''} ago"
                )

        if self._news is not None:
            await self._append_news_section(lines)

        await self._notifier.push("\n".join(lines))
        self._log.info("briefing_sent", unreviewed=unreviewed)
        await self._push_log.log("morning_brief")

    async def _append_news_section(self, lines: list[str]) -> None:
        if not self._personalization_enabled:
            await self._append_recency_news(lines)
            return

        try:
            ctx = await self._build_personalization_ctx()
        except Exception:
            await self._append_recency_news(lines)
            return

        try:
            from ze_news.types import PersonalizationContext
            relevant, discovery = await self._news.get_personalized(
                ctx=ctx,
                limit=self._briefing_news_limit,
                tags=["global"],
                min_facts=self._min_facts,
            )
        except Exception:
            await self._append_recency_news(lines)
            return

        if relevant:
            personalized = ctx.fact_count >= self._min_facts and ctx.interest_text.strip()
            header = "📰 For you (based on your interests):" if personalized else "📰 Headlines:"
            lines.append("")
            lines.append(header)
            flagged_count = 0
            for article in relevant:
                line = f"  • {article.title} ({article.source_key})"
                if self._credibility_flag_in_briefing and article.credibility and article.credibility.is_briefing_worthy:
                    flag_labels = ", ".join(f.label.lower() for f in article.credibility.high_confidence_flags)
                    line += f"  🔍 {flag_labels}"
                    flagged_count += 1
                lines.append(line)
            if (
                self._credibility_briefing_summary
                and flagged_count > 0
                and flagged_count < len(relevant) * 0.5
            ):
                lines.append(f"  ({flagged_count} of {len(relevant)} articles flagged for potentially misleading patterns)")

        if discovery:
            lines.append("")
            lines.append("🔭 Outside your usual:")
            for article in discovery:
                lines.append(f"  • {article.title} ({article.source_key})")

    async def _append_recency_news(self, lines: list[str]) -> None:
        headlines = await self._news.get_recent(limit=self._briefing_news_limit, tags=["global"])
        if headlines:
            lines.append("")
            lines.append("📰 Headlines:")
            for article in headlines:
                lines.append(f"  • {article.title} ({article.source_key})")

    async def _build_personalization_ctx(self):
        from ze_news.types import PersonalizationContext

        try:
            facts = await self._memory.list_recent_facts(days=90, limit=30)
        except Exception:
            facts = []

        goals: list[str] = []
        if self._goal_store is not None:
            try:
                goals = await self._goal_store.list_active_goal_titles()
            except Exception:
                pass

        exclusions = [
            f.value for f in facts
            if any(kw in f.predicate.lower() for kw in _EXCLUSION_KEYS)
        ]
        topic_facts = [f for f in facts if f.value not in exclusions]
        interest_parts = [f"{f.predicate}: {f.value}" for f in topic_facts]
        interest_parts += goals

        return PersonalizationContext(
            interest_text=" | ".join(interest_parts),
            exclusions=exclusions,
            explore_ratio=self._explore_ratio,
            fact_count=len(topic_facts),
        )
