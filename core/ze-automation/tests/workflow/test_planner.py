from ze_automation.workflow.planner import _parse_step


def test_parse_step_reads_on_failure():
    step = _parse_step(
        {
            "task": "Check for new items",
            "id": "s0",
            "on_failure": "continue",
            "verify": "Empty result is valid if check ran",
        },
        0,
    )
    assert step.on_failure == "continue"
    assert "Empty result" in (step.verify or "")


def test_parse_step_defaults_on_failure():
    step = _parse_step({"task": "Do work", "id": "s0"}, 0)
    assert step.on_failure == "fail"
