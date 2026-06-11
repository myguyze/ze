from __future__ import annotations

from typing import TYPE_CHECKING

from ze_core.capability.types import GateDecision, Mode
from ze_core.logging import get_logger

if TYPE_CHECKING:
    from ze_core.capability.overrides import CapabilityOverrideStore

log = get_logger(__name__)

_MODE_TO_DECISION: dict[Mode, GateDecision] = {
    Mode.AUTONOMOUS: GateDecision.EXECUTE,
    Mode.CONFIRM:    GateDecision.AWAIT_CONFIRMATION,  # → draft_response node → graph pause → await_confirmation
    Mode.DRAFT_ONLY: GateDecision.DRAFT,
    Mode.DISABLED:   GateDecision.BLOCKED,
}
# DRAFT/EXECUTE boundary: Mode.CONFIRM produces AWAIT_CONFIRMATION which routes the graph
# through draft_response (agent runs in DRAFT mode) then pauses at await_confirmation.
# The user receives a confirm_request WS frame (persisted in pending_confirmations table).
# On approval, the graph resumes via graph.ainvoke(None, config) and re-runs with EXECUTE.
# Changes to the intent_map that shift an agent from CONFIRM to AUTONOMOUS bypass this flow
# entirely — no confirmation, no audit trail. Review capability_configs carefully.

# Maximum GateDecision that a session override may reach for each base mode.
# DISABLED is handled before this table is consulted.
_MODE_CEILING: dict[Mode, GateDecision] = {
    Mode.AUTONOMOUS: GateDecision.EXECUTE,
    Mode.CONFIRM:    GateDecision.EXECUTE,
    Mode.DRAFT_ONLY: GateDecision.DRAFT,
}

# Higher rank = more permissive. Override is allowed only if its rank ≤ ceiling rank.
_DECISION_RANK: dict[GateDecision, int] = {
    GateDecision.BLOCKED:            0,
    GateDecision.DRAFT:              1,
    GateDecision.AWAIT_CONFIRMATION: 2,
    GateDecision.EXECUTE:            3,
}


def _at_or_below_ceiling(ceiling: GateDecision, requested: GateDecision) -> bool:
    return _DECISION_RANK[requested] <= _DECISION_RANK[ceiling]


class CapabilityGate:
    """
    Gate that maps (agent, intent, overrides) to a GateDecision.

    Override priority (highest to lowest):
      1. Session overrides — per-invocation, stored in AgentState, not persisted.
      2. Persistent overrides — DB-backed, survive restarts (CapabilityOverrideStore).
      3. Agent class attribute — declared in @agent class, changed by code + redeploy.

    Construct once in the container; safe to share across concurrent graph invocations.
    """

    def __init__(
        self,
        override_store: "CapabilityOverrideStore | None" = None,
    ) -> None:
        self._override_store = override_store
        # Eager cache populated at startup; invalidated on set_permanent calls.
        self._persistent_cache: dict[tuple[str, str], Mode] | None = None

    async def load_persistent_overrides(self) -> None:
        """Pre-load all DB overrides into memory. Call once at container startup."""
        if self._override_store is None:
            self._persistent_cache = {}
            return
        self._persistent_cache = await self._override_store.get_all()

    async def set_permanent(self, agent: str, intent: str, mode: Mode) -> None:
        """Persist a capability override and invalidate the cache."""
        if self._override_store is None:
            raise RuntimeError("No CapabilityOverrideStore configured")
        await self._override_store.set(agent, intent, mode)
        if self._persistent_cache is not None:
            self._persistent_cache[(agent, intent)] = mode

    async def clear_permanent(self, agent: str, intent: str) -> None:
        """Remove a persisted override and invalidate the cache."""
        if self._override_store is None:
            raise RuntimeError("No CapabilityOverrideStore configured")
        await self._override_store.clear(agent, intent)
        if self._persistent_cache is not None:
            self._persistent_cache.pop((agent, intent), None)

    def evaluate(
        self,
        agent: str,
        intent: str,
        session_overrides: dict[str, str],
    ) -> GateDecision:
        from ze_core.errors import UnknownAgentError
        from ze_core.orchestration.registry import get_agent_class

        try:
            agent_cls = get_agent_class(agent)
        except UnknownAgentError:
            log.warning("capability_unknown_agent", agent=agent)
            return GateDecision.AWAIT_CONFIRMATION

        if not getattr(agent_cls, "enabled", True):
            return GateDecision.BLOCKED

        # Base mode: persistent DB override > agent class attribute
        class_mode: Mode | None = getattr(agent_cls, "capabilities", {}).get(intent)
        persistent_mode: Mode | None = (
            self._persistent_cache.get((agent, intent))
            if self._persistent_cache is not None
            else None
        )
        mode = persistent_mode or class_mode
        if mode is None:
            log.warning("capability_unknown_intent", agent=agent, intent=intent)
            return GateDecision.AWAIT_CONFIRMATION

        if mode == Mode.DISABLED:
            return GateDecision.BLOCKED

        # Persistent overrides are treated as a code change — no ceiling applied.
        # Session override ceiling is derived from the effective mode (persistent or class).
        base = _MODE_TO_DECISION[mode]
        ceiling = _MODE_CEILING[mode]

        override_str = session_overrides.get(f"{agent}.{intent}")
        if override_str is None:
            return base

        try:
            override_mode = Mode(override_str)
        except ValueError:
            log.warning("capability_unknown_override_mode", mode=override_str)
            return base

        if override_mode == Mode.DISABLED:
            log.warning("capability_disabled_override_ignored", agent=agent, intent=intent)
            return base

        requested = _MODE_TO_DECISION[override_mode]
        return requested if _at_or_below_ceiling(ceiling, requested) else ceiling
