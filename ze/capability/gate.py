from pathlib import Path

import structlog
import yaml

from ze.capability.types import GateDecision
from ze.errors import CapabilityConfigError
from ze.logging import get_logger

# Config mode → effective GateDecision when no session override
_MODE_TO_DECISION: dict[str, GateDecision] = {
    "autonomous": GateDecision.EXECUTE,
    "confirm": GateDecision.AWAIT_CONFIRMATION,
    "draft_only": GateDecision.DRAFT,
    "disabled": GateDecision.BLOCKED,
}

# Escalation ceiling per config mode: the highest decision a session override can reach
_MODE_CEILING: dict[str, GateDecision] = {
    "autonomous": GateDecision.EXECUTE,
    "confirm": GateDecision.EXECUTE,
    "draft_only": GateDecision.DRAFT,
    "disabled": GateDecision.BLOCKED,
}

_SESSION_OVERRIDE_TO_DECISION: dict[str, GateDecision] = {
    "autonomous": GateDecision.EXECUTE,
    "confirm": GateDecision.AWAIT_CONFIRMATION,
    "draft_only": GateDecision.DRAFT,
}


class CapabilityGate:
    def __init__(
        self,
        config_path: Path,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        self._config_path = config_path
        self._log = logger or get_logger(__name__)
        self._config: dict = {}
        self._reload_strict()

    def evaluate(
        self,
        agent: str,
        intent: str,
        session_overrides: dict[str, str],
    ) -> GateDecision:
        agents = self._config.get("agents", {})
        agent_cfg = agents.get(agent, {})

        if not agent_cfg.get("enabled", True):
            self._log.info(
                "capability_blocked",
                agent=agent,
                intent=intent,
                reason="agent_disabled",
            )
            return GateDecision.BLOCKED

        capabilities = agent_cfg.get("capabilities", {})
        config_mode: str | None = capabilities.get(intent)
        if config_mode is None:
            self._log.warning(
                "capability_unknown_intent",
                agent=agent,
                intent=intent,
            )
            return GateDecision.AWAIT_CONFIRMATION

        if config_mode == "disabled":
            return GateDecision.BLOCKED

        base_decision = _MODE_TO_DECISION.get(config_mode, GateDecision.AWAIT_CONFIRMATION)
        ceiling = _MODE_CEILING.get(config_mode, GateDecision.AWAIT_CONFIRMATION)

        override_key = f"{agent}.{intent}"
        override_mode = session_overrides.get(override_key)

        if override_mode is None:
            decision = base_decision
        else:
            requested = _SESSION_OVERRIDE_TO_DECISION.get(override_mode, base_decision)
            # Enforce ceiling: session override cannot exceed what YAML allows
            decision = requested if self._decision_gte(ceiling, requested) else ceiling

        if decision in (GateDecision.BLOCKED, GateDecision.AWAIT_CONFIRMATION):
            self._log.info(
                "capability_decision",
                agent=agent,
                intent=intent,
                config_mode=config_mode,
                session_override=override_mode,
                decision=decision.value,
            )

        return decision

    def update_permanent(self, agent: str, intent: str, mode: str) -> None:
        """Atomically write a new mode for agent.intent back to config.yaml."""
        config = dict(self._config)
        agents = dict(config.get("agents", {}))
        agent_entry = dict(agents.get(agent, {}))
        capabilities = dict(agent_entry.get("capabilities", {}))
        capabilities[intent] = mode
        agent_entry["capabilities"] = capabilities
        agents[agent] = agent_entry
        config["agents"] = agents

        tmp = self._config_path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.dump(config, default_flow_style=False))
        tmp.rename(self._config_path)
        self._config = config
        self._log.info("capability_permanent_update", agent=agent, intent=intent, mode=mode)

    def reload(self) -> None:
        """Reload config from disk (call on SIGHUP). Retains previous config on error."""
        try:
            self._config = self._load()
            self._log.info("capability_config_reloaded")
        except Exception as exc:
            self._log.error("capability_config_reload_failed", error=str(exc))

    # ── Private ───────────────────────────────────────────────────────────────

    def _reload_strict(self) -> None:
        try:
            self._config = self._load()
        except Exception as exc:
            raise CapabilityConfigError(
                f"Failed to load capabilities config: {exc}"
            ) from exc

    def _load(self) -> dict:
        with open(self._config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise CapabilityConfigError("config.yaml must be a YAML mapping")
        return data

    @staticmethod
    def _decision_gte(ceiling: GateDecision, requested: GateDecision) -> bool:
        """Return True if `requested` is at or below `ceiling` in permissiveness."""
        order = [
            GateDecision.BLOCKED,
            GateDecision.DRAFT,
            GateDecision.AWAIT_CONFIRMATION,
            GateDecision.EXECUTE,
        ]
        return order.index(requested) <= order.index(ceiling)
