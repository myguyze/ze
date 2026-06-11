from __future__ import annotations

from typing import Protocol

from ze_core.capability.types import Mode


class CapabilityOverrideStore(Protocol):
    """Persistent (DB-backed) capability mode overrides.

    Overrides survive process restarts and take precedence over agent
    class-attribute modes. They replace Ze's update_permanent() / YAML
    rewrite approach with a proper database-backed mechanism.
    """

    async def get(self, agent: str, intent: str) -> Mode | None:
        """Return the override mode for (agent, intent), or None if not set."""
        ...

    async def set(self, agent: str, intent: str, mode: Mode) -> None:
        """Persist an override for (agent, intent)."""
        ...

    async def clear(self, agent: str, intent: str) -> None:
        """Remove the override for (agent, intent), reverting to the class attribute."""
        ...

    async def get_all(self) -> dict[tuple[str, str], Mode]:
        """Return all active overrides keyed by (agent, intent)."""
        ...


class PostgresCapabilityOverrideStore:
    """Postgres implementation of CapabilityOverrideStore."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def get(self, agent: str, intent: str) -> Mode | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT mode FROM capability_overrides WHERE agent = $1 AND intent = $2",
                agent, intent,
            )
        if row is None:
            return None
        try:
            return Mode(row["mode"])
        except ValueError:
            return None

    async def set(self, agent: str, intent: str, mode: Mode) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO capability_overrides (agent, intent, mode)
                VALUES ($1, $2, $3)
                ON CONFLICT (agent, intent) DO UPDATE
                    SET mode = EXCLUDED.mode, updated_at = NOW()
                """,
                agent, intent, mode.value,
            )

    async def clear(self, agent: str, intent: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM capability_overrides WHERE agent = $1 AND intent = $2",
                agent, intent,
            )

    async def get_all(self) -> dict[tuple[str, str], Mode]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT agent, intent, mode FROM capability_overrides")
        result = {}
        for row in rows:
            try:
                result[(row["agent"], row["intent"])] = Mode(row["mode"])
            except ValueError:
                pass
        return result
