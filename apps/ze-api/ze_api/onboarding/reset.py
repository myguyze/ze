from __future__ import annotations

from typing import Any

from ze_onboarding import ResetPreview, ResetResult, ResetScope

from ze_api.errors import OnboardingError

_MEMORY_TABLES = [
    "memory_relationships",
    "memory_task_state",
    "memory_procedures",
    "memory_events",
    "memory_facts",
    "memory_entities",
    "memory_episodes",
    "memory_profile_facets",
    "user_facts",
    "episodes",
    "user_profile",
]

_PERSONAL_STATE_TABLES = [
    *_MEMORY_TABLES,
    "pending_confirmations",
    "messages",
    "prospect_outreach",
    "prospect_campaigns",
    "contact_channels",
    "contact_relationships",
    "contact_sources",
    "contacts",
    "goal_execution_traces",
    "goal_suggestions",
    "goal_learnings",
    "goal_gates",
    "goal_milestones",
    "goals",
    "workflow_executions",
    "workflows",
    "user_reminders",
    "calendar_reminders",
    "insights",
    "news_articles",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
    "onboarding_seeds",
    "onboarding_steps",
    "onboarding_sessions",
]


class ResetService:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def preview(self, scope: ResetScope) -> ResetPreview:
        tables = _tables_for_scope(scope)
        counts: dict[str, int] = {}
        async with self._pool.acquire() as conn:
            existing = await _existing_tables(conn, tables)
            for table in existing:
                row = await conn.fetchrow(f"SELECT COUNT(*) AS count FROM {table}")
                counts[table] = int(row["count"])
        return ResetPreview(scope=scope, counts=counts)

    async def reset(self, scope: ResetScope, *, confirm: str) -> ResetResult:
        if confirm != "RESET":
            raise OnboardingError("Reset requires confirm='RESET'")

        preview = await self.preview(scope)
        if not preview.counts:
            return ResetResult(scope=scope, deleted={})

        async with self._pool.acquire() as conn:
            table_sql = ", ".join(preview.counts)
            await conn.execute(f"TRUNCATE {table_sql} RESTART IDENTITY CASCADE")
            if "user_profile" in preview.counts:
                await conn.execute(
                    """
                    INSERT INTO user_profile (id)
                    VALUES (1)
                    ON CONFLICT DO NOTHING
                    """
                )
        return ResetResult(scope=scope, deleted=preview.counts)


def _tables_for_scope(scope: ResetScope) -> list[str]:
    if scope == "memory":
        return _MEMORY_TABLES
    if scope == "personal_state":
        return _PERSONAL_STATE_TABLES
    if scope == "full_dev":
        raise OnboardingError("full_dev reset is not supported through ResetService")
    raise OnboardingError(f"Unknown reset scope: {scope}")


async def _existing_tables(conn: Any, tables: list[str]) -> list[str]:
    existing: list[str] = []
    for table in tables:
        row = await conn.fetchrow("SELECT to_regclass($1) AS name", table)
        if row is not None and row["name"] is not None:
            existing.append(table)
    return existing
