import asyncpg

from ze.logging import get_logger
from ze.proactive.notifier import ProactiveNotifier
from ze.settings import Settings
from ze.telemetry.context import set_flow_context


class MorningBriefing:
    def __init__(
        self,
        notifier: ProactiveNotifier,
        pool: asyncpg.Pool,
        settings: Settings,
    ) -> None:
        self._notifier = notifier
        self._pool = pool
        self._settings = settings
        self._log = get_logger(__name__)
        follow_up_cfg = settings.contacts_config.get("follow_up", {})
        self._stale_days = int(follow_up_cfg.get("stale_days", 7))
        self._max_nudges = int(follow_up_cfg.get("max_nudges", 3))

    async def run(self) -> None:
        set_flow_context("morning_briefing")
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT 1 FROM push_log WHERE event_type = 'morning_brief' "
                "AND sent_at > NOW() - INTERVAL '20 hours'"
            )
            if existing:
                self._log.info("briefing_skipped_dedup")
                return

            unreviewed_row = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM user_facts WHERE reviewed = false AND contradicted = false"
            )
            workflow_rows = await conn.fetch(
                "SELECT name FROM workflows WHERE enabled = true AND schedule IS NOT NULL ORDER BY name"
            )
            failure_rows = await conn.fetch(
                "SELECT payload, sent_at FROM push_log "
                "WHERE event_type LIKE 'workflow_failure:%' "
                "AND sent_at > NOW() - INTERVAL '24 hours' "
                "ORDER BY sent_at DESC"
            )
            stale_contact_rows = await conn.fetch(
                """
                SELECT name,
                       EXTRACT(DAY FROM NOW() - last_mentioned)::int AS days_ago
                FROM contacts
                WHERE confirmed = true
                  AND dismissed = false
                  AND last_mentioned IS NOT NULL
                  AND last_mentioned < NOW() - ($1 || ' days')::interval
                ORDER BY last_mentioned ASC
                LIMIT $2
                """,
                str(self._stale_days),
                self._max_nudges,
            )

        unreviewed = unreviewed_row["n"]
        threshold = int(
            self._settings.proactive_config.get("briefing", {}).get("unreviewed_nudge_threshold", 5)
        )

        lines = ["Good morning! Here's your Ze briefing.", ""]
        lines.append(f"📋 Unreviewed facts: {unreviewed}")

        if workflow_rows:
            names = ", ".join(r["name"] for r in workflow_rows)
            lines.append(f"⚙️  Scheduled workflows: {names}")
        else:
            lines.append("⚙️  Scheduled workflows: none")

        if failure_rows:
            lines.append("")
            for row in failure_rows:
                name = row["payload"] or "unknown"
                when = row["sent_at"].strftime("%H:%M UTC")
                lines.append(f"⚠️  Recent failure: {name} at {when}")

        if unreviewed >= threshold:
            lines.append("")
            lines.append(f"💡 You have {unreviewed} facts waiting for review.")

        if stale_contact_rows:
            lines.append("")
            lines.append("📌 Follow-up nudges:")
            for row in stale_contact_rows:
                days = row["days_ago"]
                lines.append(f"  • {row['name']} — last mentioned {days} day{'s' if days != 1 else ''} ago")

        await self._notifier.push("\n".join(lines))
        self._log.info("briefing_sent", unreviewed=unreviewed)

        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO push_log (event_type) VALUES ('morning_brief')"
            )
