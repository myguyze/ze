import pytest

from ze_core.capability import CapabilityGate, GateDecision, Mode
from ze_core.orchestration import agent, clear_registry
from ze_core.orchestration.types import AgentContext, AgentResult


@pytest.fixture(autouse=True)
def clean_registry():
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def gate():
    return CapabilityGate()


def _register(name: str, capabilities: dict, enabled: bool = True) -> None:
    class _A:
        async def run(self, ctx: AgentContext) -> AgentResult:
            return AgentResult(agent=name, response="")

    _A.__name__ = f"Agent_{name}"
    _A.name = name
    _A.description = f"Agent {name}"
    _A.enabled = enabled
    _A.capabilities = capabilities
    agent(_A)


# ── Base mode → decision ──────────────────────────────────────────────────────

class TestBaseModeDecision:
    def test_autonomous_returns_execute(self, gate):
        _register("a", {"read": Mode.AUTONOMOUS})
        assert gate.evaluate("a", "read", {}) == GateDecision.EXECUTE

    def test_confirm_returns_await_confirmation(self, gate):
        _register("a", {"write": Mode.CONFIRM})
        assert gate.evaluate("a", "write", {}) == GateDecision.AWAIT_CONFIRMATION

    def test_draft_only_returns_draft(self, gate):
        _register("a", {"send": Mode.DRAFT_ONLY})
        assert gate.evaluate("a", "send", {}) == GateDecision.DRAFT

    def test_disabled_returns_blocked(self, gate):
        _register("a", {"delete": Mode.DISABLED})
        assert gate.evaluate("a", "delete", {}) == GateDecision.BLOCKED


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_agent_returns_await_confirmation(self, gate):
        assert gate.evaluate("ghost", "read", {}) == GateDecision.AWAIT_CONFIRMATION

    def test_disabled_agent_returns_blocked(self, gate):
        _register("a", {"read": Mode.AUTONOMOUS}, enabled=False)
        assert gate.evaluate("a", "read", {}) == GateDecision.BLOCKED

    def test_unknown_intent_returns_await_confirmation(self, gate):
        _register("a", {"read": Mode.AUTONOMOUS})
        assert gate.evaluate("a", "nonexistent", {}) == GateDecision.AWAIT_CONFIRMATION

    def test_disabled_mode_cannot_be_overridden(self, gate):
        _register("a", {"delete": Mode.DISABLED})
        assert gate.evaluate("a", "delete", {"a.delete": "autonomous"}) == GateDecision.BLOCKED

    def test_unknown_override_mode_falls_back_to_base(self, gate):
        _register("a", {"read": Mode.CONFIRM})
        assert gate.evaluate("a", "read", {"a.read": "telepathy"}) == GateDecision.AWAIT_CONFIRMATION

    def test_disabled_override_value_ignored(self, gate):
        _register("a", {"read": Mode.CONFIRM})
        assert gate.evaluate("a", "read", {"a.read": "disabled"}) == GateDecision.AWAIT_CONFIRMATION


# ── Session overrides — escalation ceiling table ──────────────────────────────

class TestEscalationCeiling:
    def test_autonomous_no_override(self, gate):
        _register("a", {"op": Mode.AUTONOMOUS})
        assert gate.evaluate("a", "op", {}) == GateDecision.EXECUTE

    def test_autonomous_restricted_to_confirm(self, gate):
        _register("a", {"op": Mode.AUTONOMOUS})
        assert gate.evaluate("a", "op", {"a.op": "confirm"}) == GateDecision.AWAIT_CONFIRMATION

    def test_autonomous_restricted_to_draft(self, gate):
        _register("a", {"op": Mode.AUTONOMOUS})
        assert gate.evaluate("a", "op", {"a.op": "draft_only"}) == GateDecision.DRAFT

    def test_confirm_no_override(self, gate):
        _register("a", {"op": Mode.CONFIRM})
        assert gate.evaluate("a", "op", {}) == GateDecision.AWAIT_CONFIRMATION

    def test_confirm_escalated_to_autonomous(self, gate):
        _register("a", {"op": Mode.CONFIRM})
        assert gate.evaluate("a", "op", {"a.op": "autonomous"}) == GateDecision.EXECUTE

    def test_confirm_restricted_to_draft(self, gate):
        _register("a", {"op": Mode.CONFIRM})
        assert gate.evaluate("a", "op", {"a.op": "draft_only"}) == GateDecision.DRAFT

    def test_draft_only_no_override(self, gate):
        _register("a", {"op": Mode.DRAFT_ONLY})
        assert gate.evaluate("a", "op", {}) == GateDecision.DRAFT

    def test_draft_only_ceiling_blocks_autonomous(self, gate):
        _register("a", {"op": Mode.DRAFT_ONLY})
        assert gate.evaluate("a", "op", {"a.op": "autonomous"}) == GateDecision.DRAFT

    def test_draft_only_ceiling_blocks_confirm(self, gate):
        _register("a", {"op": Mode.DRAFT_ONLY})
        assert gate.evaluate("a", "op", {"a.op": "confirm"}) == GateDecision.DRAFT


# ── Override key scoping ──────────────────────────────────────────────────────

class TestOverrideKeyScoping:
    def test_override_only_applies_to_matching_agent_intent(self, gate):
        _register("cal", {"read": Mode.CONFIRM, "write": Mode.CONFIRM})
        result = gate.evaluate("cal", "write", {"cal.read": "autonomous"})
        assert result == GateDecision.AWAIT_CONFIRMATION

    def test_override_for_different_agent_ignored(self, gate):
        _register("cal", {"read": Mode.CONFIRM})
        _register("email", {"read": Mode.CONFIRM})
        assert gate.evaluate("cal", "read", {"email.read": "autonomous"}) == GateDecision.AWAIT_CONFIRMATION
