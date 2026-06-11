import asyncio
import json
from datetime import date, timedelta

import asyncpg

from ze_core.logging import get_logger
from ze_core.openrouter.client import OpenRouterClient
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.settings import Settings
from ze_core.proactive.job import proactive_job
from ze_core.telemetry.context import set_agent_context, set_flow_context

_VALID_CATEGORIES = {"pattern", "trend", "goal", "tension"}

_SYSTEM = """\
You are Ze's insight engine. Based on the user's recent activity, identify 1-3
specific observations worth surfacing. Each insight must:
- Reference concrete evidence (specific topics, exact counts, named patterns)
- Be genuinely novel — not already present in the "recent insights" list below
- Be phrased conversationally, as Ze speaking warmly to the user (1-2 sentences)
- End with a gentle open question where natural (not forced)

Return a JSON array of objects with exactly two string keys:
  "text": the observation as Ze would say it
  "category": one of "pattern", "trend", "goal", "tension"

Return [] if there is truly nothing worth surfacing this week.\
"""


@proactive_job
class InsightEngine:
    job_id = "insight_generation"
    def __init__(
        self,
        notifier: ProactiveNotifier,
        pool: asyncpg.Pool,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._notifier = notifier
        self._pool = pool
        self._client = openrouter_client
        self._settings = settings
        self._log = get_logger(__name__)

    async def run(self) -> None:
        """Weekly job: generate insights from recent evidence and push any novel ones."""
        set_flow_context("insight_generation")
        set_agent_context("insights")
        insight_mem_cfg = self._settings.config.get("proactive", {}).get("insights", {})
        lookback_days = int(insight_mem_cfg.get("lookback_days", 7))
        min_evidence = int(insight_mem_cfg.get("min_evidence", 3))
        max_per_run = int(insight_mem_cfg.get("max_per_run", 3))

        cooldown_days = int(
            self._settings.config.get("proactive", {}).get("insights", {}).get("category_cooldown_days", 7)
        )
        model = self._settings.config.get("models", {}).get(
            "insights", "anthropic/claude-haiku-4-5"
        )

        week_of = date.today() - timedelta(days=date.today().weekday())

        async with self._pool.acquire() as conn:
            fact_rows = await conn.fetch(
                "SELECT key, value, updated_at FROM user_facts "
                "WHERE contradicted = false "
                "AND updated_at > NOW() - ($1 * INTERVAL '1 day') "
                "ORDER BY updated_at DESC",
                lookback_days,
            )
            episode_rows = await conn.fetch(
                "SELECT summary, response, created_at FROM episodes "
                "WHERE created_at > NOW() - ($1 * INTERVAL '1 day') "
                "AND is_archive = false "
                "ORDER BY created_at DESC",
                lookback_days,
            )
            profile_row = await conn.fetchrow(
                "SELECT preferences, habits, topics, relationships, goals "
                "FROM user_profile WHERE id = 1"
            )
            recent_insight_rows = await conn.fetch(
                "SELECT text, category FROM insights "
                "ORDER BY created_at DESC LIMIT 20"
            )
            pushed_category_rows = await conn.fetch(
                "SELECT DISTINCT category FROM insights "
                "WHERE pushed = true "
                "AND pushed_at > NOW() - ($1 * INTERVAL '1 day')",
                cooldown_days,
            )

        if len(fact_rows) + len(episode_rows) < min_evidence:
            self._log.info("insights_skipped_sparse", facts=len(fact_rows), episodes=len(episode_rows))
            return

        recently_pushed_categories = {r["category"] for r in pushed_category_rows}

        profile_block = _render_profile(profile_row)
        facts_block = _render_facts(fact_rows)
        episodes_block = _render_episodes(episode_rows)
        recent_insights_block = _render_recent_insights(recent_insight_rows)

        user_prompt = (
            f"User profile:\n{profile_block}\n\n"
            f"Facts from the past {lookback_days} days:\n{facts_block}\n\n"
            f"Recent interaction summaries (past {lookback_days} days):\n{episodes_block}\n\n"
            f"Recent insights already surfaced (avoid repetition):\n{recent_insights_block}\n\n"
            "Generate insights."
        )

        try:
            raw = await self._client.complete(
                model=model,
                system=_SYSTEM,
                prompt=user_prompt,
                max_tokens=400,
            )
        except Exception as exc:
            self._log.warning("insights_llm_failed", error=str(exc))
            return

        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                raise ValueError("not a list")
        except Exception:
            self._log.warning("insights_bad_json", raw=raw[:200])
            return

        valid: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            category = item.get("category", "")
            if not text or not isinstance(text, str):
                continue
            if category not in _VALID_CATEGORIES:
                continue
            if category in recently_pushed_categories:
                continue
            valid.append({"text": text, "category": category})

        valid = valid[:max_per_run]

        if not valid:
            return

        async with self._pool.acquire() as conn:
            for insight in valid:
                row = await conn.fetchrow(
                    "INSERT INTO insights (text, category, week_of) VALUES ($1, $2, $3) RETURNING id",
                    insight["text"],
                    insight["category"],
                    week_of,
                )
                await self._notifier.push(insight["text"])
                await conn.execute(
                    "UPDATE insights SET pushed = true, pushed_at = NOW() WHERE id = $1",
                    row["id"],
                )
                self._log.info(
                    "insight_pushed",
                    category=insight["category"],
                    preview=insight["text"][:80],
                )
                await asyncio.sleep(1)


def _render_profile(row) -> str:
    if row is None:
        return "(no profile yet)"
    parts = []
    for field in ("preferences", "habits", "topics", "relationships", "goals"):
        val = row[field] or ""
        if val.strip():
            parts.append(f"**{field.capitalize()}:** {val}")
    return "\n".join(parts) if parts else "(no profile yet)"


def _render_facts(rows) -> str:
    if not rows:
        return "(none)"
    return "\n".join(f"- {r['key']}: {r['value']}" for r in rows)


def _render_episodes(rows) -> str:
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        text = r["summary"] or (r["response"] or "")[:200]
        lines.append(f"- {text}")
    return "\n".join(lines)


def _render_recent_insights(rows) -> str:
    if not rows:
        return "(none)"
    return "\n".join(f"- [{r['category']}] {r['text']}" for r in rows)
