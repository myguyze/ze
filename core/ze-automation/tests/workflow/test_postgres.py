from ze_automation.workflow.postgres import (
    _step_from_dict,
    _step_result_from_dict,
    _step_result_to_dict,
    _step_to_dict,
)
from ze_automation.workflow.types import StepResult, WorkflowStep


def test_step_round_trip_on_failure():
    step = WorkflowStep(task="monitor", id="s0", on_failure="continue")
    data = _step_to_dict(step)
    assert "on_failure" in data
    restored = _step_from_dict(data, 0)
    assert restored.on_failure == "continue"


def test_step_from_dict_defaults_on_failure_to_fail():
    restored = _step_from_dict({"task": "x", "id": "s0"}, 0)
    assert restored.on_failure == "fail"


def test_step_result_round_trip_new_fields():
    result = StepResult(
        step_index=0,
        task="monitor",
        output="nothing new",
        success=True,
        error=None,
        duration_ms=100,
        step_id="s0",
        attempt_count=2,
        no_results=True,
    )
    data = _step_result_to_dict(result)
    assert data["attempt_count"] == 2
    assert data["no_results"] is True
    restored = _step_result_from_dict(data)
    assert restored.attempt_count == 2
    assert restored.no_results is True


def test_step_result_from_dict_defaults():
    restored = _step_result_from_dict(
        {
            "step_index": 0,
            "task": "x",
            "success": True,
            "error": None,
            "duration_ms": 0,
        }
    )
    assert restored.attempt_count == 1
    assert restored.no_results is False
