from __future__ import annotations

from ze_core import defaults
from ze_core.db import DBPool
from ze_core.errors import UnknownDialError, UnknownProfileError
from ze_core.logging import get_logger
from ze_personal.persona.types import PersonaState

log = get_logger(__name__)


class PostgresPersonaStore:
    """Postgres-backed PersonaStore.

    Profiles are loaded from a dict (typically parsed from persona.yaml or
    config.yaml). Dial overrides are persisted in the persona_state table.
    """

    def __init__(
        self,
        pool: DBPool,
        profiles: dict[str, dict],
        known_dials: frozenset[str] = defaults.PERSONA_KNOWN_DIALS,
        default_profile: str = defaults.PERSONA_DEFAULT_PROFILE,
    ) -> None:
        self._pool = pool
        self._profiles = profiles  # name → profile dict
        self._known_dials = known_dials
        self._default_profile = default_profile

    # ── Public ────────────────────────────────────────────────────────────────

    async def get_active(self) -> dict:
        """Return the active profile dict with DB dial overrides merged in."""
        state = await self.get_state()
        profile = self._resolve_profile(state.profile)
        if state.dials:
            merged = {**profile.get("dials", {}), **state.dials}
            return {**profile, "dials": merged}
        return profile

    async def get_state(self) -> PersonaState:
        """Return the raw DB state (profile name + dial overrides)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT profile, dials, updated_at FROM persona_state WHERE id = 1"
            )
        if row is None:
            return PersonaState(profile=self._default_profile)
        return PersonaState(
            profile=row["profile"],
            dials=dict(row["dials"] or {}),
            updated_at=row["updated_at"],
        )

    async def set_profile(self, name: str) -> None:
        """Switch to a named profile and clear dial overrides."""
        if name not in self._profiles:
            raise UnknownProfileError(
                f"Unknown profile {name!r}. Available: {list(self._profiles)}"
            )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE persona_state SET profile = $1, dials = '{}', updated_at = NOW() WHERE id = 1",
                name,
            )
        log.info("persona_profile_set", profile=name)

    async def set_dial(self, name: str, value: float) -> None:
        """Override one dial on the current profile."""
        if name not in self._known_dials:
            raise UnknownDialError(
                f"Unknown dial {name!r}. Known dials: {sorted(self._known_dials)}"
            )
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Dial value must be in [0.0, 1.0], got {value}")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE persona_state
                SET dials = dials || jsonb_build_object($1::text, $2::float),
                    updated_at = NOW()
                WHERE id = 1
                """,
                name,
                value,
            )
        log.info("persona_dial_set", dial=name, value=value)

    async def reset_dials(self) -> None:
        """Restore all dials to the active profile's defaults."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE persona_state SET dials = '{}', updated_at = NOW() WHERE id = 1"
            )
        log.info("persona_dials_reset")

    def available_profiles(self) -> list[str]:
        return list(self._profiles)

    # ── Private ───────────────────────────────────────────────────────────────

    def _resolve_profile(self, name: str) -> dict:
        if self._profiles:
            return dict(self._profiles.get(name) or next(iter(self._profiles.values())))
        return {
            "traits": ["direct", "warm", "concise"],
            "verbosity": "concise",
            "custom_instructions": "",
            "dials": {},
        }
