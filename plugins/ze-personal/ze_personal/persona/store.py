from __future__ import annotations

from typing import Protocol

from ze_personal.persona.types import PersonaState


class PersonaStore(Protocol):
    """Protocol for persona state persistence."""

    async def get_active(self) -> dict:
        """Return the active profile dict with DB dial overrides merged in."""
        ...

    async def get_state(self) -> PersonaState:
        """Return the raw persisted state (profile name + dial overrides)."""
        ...

    async def set_profile(self, name: str) -> None:
        """Switch to a named profile and clear dial overrides."""
        ...

    async def set_dial(self, name: str, value: float) -> None:
        """Override one dial on the current profile."""
        ...

    async def reset_dials(self) -> None:
        """Restore all dials to the active profile's defaults."""
        ...

    def available_profiles(self) -> list[str]:
        """Names of all profiles known to this store."""
        ...
