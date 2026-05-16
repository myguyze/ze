import pytest
import yaml

from ze.capability.gate import CapabilityGate
from ze.capability.types import GateDecision
from ze.errors import CapabilityConfigError
from ze.logging import configure_logging


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture
def config_file(tmp_path):
    """Write a standard capabilities.yaml and return a factory for the gate."""
    cfg = {
        "capabilities": {
            "research": {
                "enabled": True,
                "read": "autonomous",
                "reason": "confirm",
            },
            "companion": {
                "enabled": True,
                "reason": "autonomous",
                "create": "draft_only",
            },
            "calendar": {
                "enabled": False,
                "read": "autonomous",
                "create": "confirm",
            },
        }
    }
    path = tmp_path / "capabilities.yaml"
    path.write_text(yaml.dump(cfg))
    return path


def make_gate(path) -> CapabilityGate:
    return CapabilityGate(config_path=path)


# ── Construction ──────────────────────────────────────────────────────────────

def test_gate_loads_config(config_file):
    gate = make_gate(config_file)
    assert gate._config is not None


def test_gate_raises_on_missing_file(tmp_path):
    with pytest.raises(CapabilityConfigError):
        CapabilityGate(config_path=tmp_path / "nonexistent.yaml")


def test_gate_raises_on_invalid_yaml(tmp_path):
    bad = tmp_path / "capabilities.yaml"
    bad.write_text("- this is a list not a mapping")
    with pytest.raises(CapabilityConfigError):
        CapabilityGate(config_path=bad)


# ── evaluate() — basic decisions ─────────────────────────────────────────────

def test_autonomous_returns_execute(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("research", "read", {}) == GateDecision.EXECUTE


def test_confirm_returns_await_confirmation(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("research", "reason", {}) == GateDecision.AWAIT_CONFIRMATION


def test_draft_only_returns_draft(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("companion", "create", {}) == GateDecision.DRAFT


def test_disabled_agent_returns_blocked(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("calendar", "read", {}) == GateDecision.BLOCKED


def test_disabled_agent_blocked_regardless_of_override(config_file):
    gate = make_gate(config_file)
    overrides = {"calendar.read": "autonomous"}
    assert gate.evaluate("calendar", "read", overrides) == GateDecision.BLOCKED


def test_unknown_intent_returns_await_confirmation(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("research", "delete", {}) == GateDecision.AWAIT_CONFIRMATION


def test_unknown_agent_returns_await_confirmation(config_file):
    gate = make_gate(config_file)
    assert gate.evaluate("ghost_agent", "read", {}) == GateDecision.AWAIT_CONFIRMATION


# ── evaluate() — session override escalation ──────────────────────────────────

def test_confirm_escalated_to_execute_by_session(config_file):
    gate = make_gate(config_file)
    overrides = {"research.reason": "autonomous"}
    assert gate.evaluate("research", "reason", overrides) == GateDecision.EXECUTE


def test_autonomous_restricted_to_confirm_by_session(config_file):
    gate = make_gate(config_file)
    overrides = {"research.read": "confirm"}
    assert gate.evaluate("research", "read", overrides) == GateDecision.AWAIT_CONFIRMATION


def test_draft_only_ceiling_blocks_autonomous_override(config_file):
    """Session cannot escalate draft_only to autonomous — ceiling enforced."""
    gate = make_gate(config_file)
    overrides = {"companion.create": "autonomous"}
    assert gate.evaluate("companion", "create", overrides) == GateDecision.DRAFT


def test_draft_only_ceiling_blocks_confirm_override(config_file):
    """Session cannot escalate draft_only to confirm — ceiling enforced."""
    gate = make_gate(config_file)
    overrides = {"companion.create": "confirm"}
    assert gate.evaluate("companion", "create", overrides) == GateDecision.DRAFT


# ── update_permanent() ────────────────────────────────────────────────────────

def test_update_permanent_changes_mode(config_file):
    gate = make_gate(config_file)
    gate.update_permanent("research", "reason", "autonomous")
    assert gate.evaluate("research", "reason", {}) == GateDecision.EXECUTE


def test_update_permanent_writes_file(config_file):
    gate = make_gate(config_file)
    gate.update_permanent("companion", "reason", "confirm")
    reloaded = yaml.safe_load(config_file.read_text())
    assert reloaded["capabilities"]["companion"]["reason"] == "confirm"


def test_update_permanent_atomic_write(config_file):
    """Temp file should not be left behind after write."""
    gate = make_gate(config_file)
    gate.update_permanent("research", "read", "confirm")
    tmp = config_file.with_suffix(".yaml.tmp")
    assert not tmp.exists()


# ── reload() ─────────────────────────────────────────────────────────────────

def test_reload_picks_up_changes(config_file):
    gate = make_gate(config_file)
    cfg = yaml.safe_load(config_file.read_text())
    cfg["capabilities"]["research"]["read"] = "confirm"
    config_file.write_text(yaml.dump(cfg))
    gate.reload()
    assert gate.evaluate("research", "read", {}) == GateDecision.AWAIT_CONFIRMATION


def test_reload_retains_config_on_error(config_file):
    gate = make_gate(config_file)
    config_file.write_text("not: valid: yaml: [")
    gate.reload()  # should not raise
    # Previous config still works
    assert gate.evaluate("research", "read", {}) == GateDecision.EXECUTE
