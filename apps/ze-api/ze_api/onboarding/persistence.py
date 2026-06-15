from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from ze_memory.types import Fact
from ze_onboarding import StoredOnboardingSeed

from ze_api.errors import OnboardingError

PluginSettingSetter = Callable[[str, Any], Awaitable[None]]


class OnboardingPersistence:
    def __init__(
        self,
        *,
        memory_store: Any,
        plugin_setting_setters: dict[str, PluginSettingSetter] | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._plugin_setting_setters = plugin_setting_setters or {}

    async def apply(self, seeds: list[StoredOnboardingSeed]) -> list[StoredOnboardingSeed]:
        applied: list[StoredOnboardingSeed] = []
        for seed in seeds:
            if seed.kind == "memory_fact":
                await self._apply_memory_fact(seed)
            elif seed.kind == "profile_facet":
                await self._apply_profile_facet(seed)
            elif seed.kind == "plugin_setting":
                await self._apply_plugin_setting(seed)
            else:
                raise OnboardingError(f"Unsupported onboarding seed kind: {seed.kind}")
            applied.append(seed)
        return applied

    async def _apply_memory_fact(self, seed: StoredOnboardingSeed) -> None:
        await self._memory_store.propose_facts([
            Fact(
                predicate=seed.key,
                value=_seed_value_text(seed.value),
                confidence=seed.confidence,
                reviewed=True,
            )
        ])

    async def _apply_profile_facet(self, seed: StoredOnboardingSeed) -> None:
        await self._memory_store.upsert_profile_facets([{
            "key": seed.key,
            "value": _seed_value_text(seed.value),
            "stability": "stable",
            "confidence": seed.confidence,
        }])

    async def _apply_plugin_setting(self, seed: StoredOnboardingSeed) -> None:
        if seed.plugin is None:
            raise OnboardingError("Plugin setting seed is missing plugin name")
        setter = self._plugin_setting_setters.get(seed.plugin)
        if setter is None:
            raise OnboardingError(f"No onboarding setting setter registered for {seed.plugin}")
        await setter(seed.key, seed.value)


def _seed_value_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)
