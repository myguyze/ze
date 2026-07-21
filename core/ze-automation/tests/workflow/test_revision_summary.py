from ze_automation.workflow.revision_summary import build_change_summary
from ze_automation.workflow.types import Branch, WorkflowStep


def _step(**kwargs) -> WorkflowStep:
    defaults = dict(task="do thing", id="s1")
    defaults.update(kwargs)
    return WorkflowStep(**defaults)


def test_created_summary():
    after = [_step(id="s1"), _step(id="s2")]
    summary = build_change_summary([], after, "created")
    assert summary == "Workflow created with 2 step(s)"


def test_step_added():
    before = [_step(id="s1")]
    after = [_step(id="s1"), _step(id="s2")]
    summary = build_change_summary(before, after, "edited")
    assert summary == "Step s2 added"


def test_step_removed():
    before = [_step(id="s1"), _step(id="s2")]
    after = [_step(id="s1")]
    summary = build_change_summary(before, after, "edited")
    assert summary == "Step s2 removed"


def test_field_change_on_failure_phrasing():
    before = [_step(id="s1", on_failure="fail")]
    after = [_step(id="s1", on_failure="continue")]
    summary = build_change_summary(before, after, "edited")
    assert summary == "Step s1: on_failure fail → continue"


def test_multiple_field_changes_joined_with_semicolon():
    before = [_step(id="s1", task="old task", on_failure="fail")]
    after = [_step(id="s1", task="new task", on_failure="continue")]
    summary = build_change_summary(before, after, "edited")
    assert (
        summary
        == "Step s1: task old task → new task; Step s1: on_failure fail → continue"
    )


def test_branches_change_detected():
    before = [_step(id="s1", branches=[])]
    after = [_step(id="s1", branches=[Branch(condition="ok", to="s2")])]
    summary = build_change_summary(before, after, "edited")
    assert "branches" in summary


def test_no_change_yields_empty_summary():
    before = [_step(id="s1")]
    after = [_step(id="s1")]
    summary = build_change_summary(before, after, "edited")
    assert summary == ""
