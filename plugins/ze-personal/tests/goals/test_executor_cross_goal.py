from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_personal.goals.executor import GoalExecutor, _build_milestone_prompt
from ze_personal.goals.types import (
    Goal,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    PriorMilestoneOutput,
    VerificationGate,
)


def _goal(status=GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id=uuid4(),
        title="Build product",
        objective="Ship MVP",
        success_condition="First customer",
        status=status,
    )


def _milestone(seq=1, status=MilestoneStatus.PENDING, reuse_hint="") -> Milestone:
    return Milestone(
        id=uuid4(),
        goal_id=uuid4(),
        title=f"Step {seq}",
        description=f"Do step {seq}",
        sequence=seq,
        status=status,
        reuse_hint=reuse_hint,
    )


def _prior() -> PriorMilestoneOutput:
    return PriorMilestoneOutput(
        goal_id=uuid4(),
        goal_title="Old Goal",
        milestone_id=uuid4(),
        milestone_title="Survey market",
        output_snippet="Found 12 competitors.",
        completed_days_ago=5,
    )


def _make_executor(*, store=None, planner=None, push=None):
    store = store or AsyncMock()
    planner = planner or AsyncMock()
    push = push or AsyncMock()
    agent_getter = MagicMock(return_value=AsyncMock())
    executor = GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=agent_getter,
    )
    return executor, store, planner, push


def _make_store(
    *,
    goal=None,
    milestones=None,
    prior_work=None,
    prior_work_raises=False,
):
    store = AsyncMock()
    store.get_goal = AsyncMock(return_value=goal or _goal())
    store.list_milestones = AsyncMock(return_value=milestones or [])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.list_completed_milestone_summaries = (
        AsyncMock(side_effect=RuntimeError("DB error"))
        if prior_work_raises
        else AsyncMock(return_value=prior_work or [])
    )
    store.replace_pending_milestones = AsyncMock(return_value=[])
    store.replace_pending_gates = AsyncMock(return_value=[])
    store.resolve_gate = AsyncMock()
    store.update_status = AsyncMock()
    store.add_learning = AsyncMock()
    store.append_learnings = AsyncMock()
    store.reset_consecutive_failures = AsyncMock()
    return store


# ── _build_milestone_prompt ───────────────────────────────────────────────────

def test_build_milestone_prompt_appends_prior_work_section_when_hint_set():
    m = _milestone(reuse_hint="Prior goal 'X' did this 5 days ago.")
    goal = _goal()
    prompt = _build_milestone_prompt(m, goal, [m])
    assert "[PRIOR WORK FROM OTHER GOALS]" in prompt
    assert "Prior goal 'X' did this 5 days ago." in prompt


def test_build_milestone_prompt_omits_prior_work_section_when_hint_empty():
    m = _milestone(reuse_hint="")
    goal = _goal()
    prompt = _build_milestone_prompt(m, goal, [m])
    assert "[PRIOR WORK FROM OTHER GOALS]" not in prompt


def test_build_milestone_prompt_prior_work_appended_after_task(caplog):
    hint = "Some hint"
    m = _milestone(reuse_hint=hint)
    goal = _goal()
    prompt = _build_milestone_prompt(m, goal, [m])
    task_pos = prompt.index("[YOUR TASK]")
    prior_pos = prompt.index("[PRIOR WORK FROM OTHER GOALS]")
    assert prior_pos > task_pos


def test_build_milestone_prompt_emits_log_when_hint_set():
    import structlog.testing
    m = _milestone(reuse_hint="Some hint")
    goal = _goal()
    with structlog.testing.capture_logs() as logs:
        _build_milestone_prompt(m, goal, [m])
    assert any(l.get("event") == "goal_reuse_hint_used" for l in logs)


# ── _fetch_prior_work ─────────────────────────────────────────────────────────

async def test_fetch_prior_work_returns_empty_and_logs_on_store_failure():
    import structlog.testing
    store = _make_store(prior_work_raises=True)
    executor, _, _, _ = _make_executor(store=store)

    with structlog.testing.capture_logs() as logs:
        result = await executor._fetch_prior_work(uuid4())

    assert result == []
    assert any(l.get("event") == "goal_prior_work_query_failed" for l in logs)


async def test_fetch_prior_work_returns_results_on_success():
    pw = _prior()
    store = _make_store(prior_work=[pw])
    executor, _, _, _ = _make_executor(store=store)

    result = await executor._fetch_prior_work(uuid4())
    assert result == [pw]


# ── _apply_steer ──────────────────────────────────────────────────────────────

async def test_apply_steer_passes_prior_work_to_replan():
    pw = _prior()
    goal = _goal()
    completed = [_milestone(seq=1, status=MilestoneStatus.COMPLETED)]
    store = _make_store(goal=goal, milestones=completed, prior_work=[pw])

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, _ = _make_executor(store=store, planner=planner)
    await executor._apply_steer(goal.id, goal, "New direction")

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") == [pw]


async def test_apply_steer_passes_none_when_no_prior_work():
    goal = _goal()
    store = _make_store(goal=goal, milestones=[], prior_work=[])

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, _ = _make_executor(store=store, planner=planner)
    await executor._apply_steer(goal.id, goal, "instruction")

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") is None


# ── _trigger_adaptive_replan ──────────────────────────────────────────────────

async def test_trigger_adaptive_replan_passes_prior_work():
    pw = _prior()
    goal = _goal()
    completed = [_milestone(seq=1, status=MilestoneStatus.COMPLETED)]
    store = _make_store(goal=goal, milestones=completed, prior_work=[pw])

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, push = _make_executor(store=store, planner=planner)
    await executor._trigger_adaptive_replan(goal, completed)

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") == [pw]


async def test_trigger_adaptive_replan_passes_none_when_no_prior_work():
    goal = _goal()
    store = _make_store(goal=goal, prior_work=[])

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, _ = _make_executor(store=store, planner=planner)
    await executor._trigger_adaptive_replan(goal, [])

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") is None


# ── handle_gate_redirected ────────────────────────────────────────────────────

async def test_handle_gate_redirected_passes_prior_work():
    pw = _prior()
    goal = _goal()
    gate_id = uuid4()
    gate = VerificationGate(
        id=gate_id,
        goal_id=goal.id,
        after_sequence=1,
        title="Checkpoint",
        status=GateStatus.AWAITING_APPROVAL,
    )
    completed = [_milestone(seq=1, status=MilestoneStatus.COMPLETED)]
    store = _make_store(goal=goal, milestones=completed, prior_work=[pw])
    store.get_gate = AsyncMock(return_value=gate)

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, _ = _make_executor(store=store, planner=planner)
    await executor.handle_gate_redirected(gate_id, "Go a different direction")

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") == [pw]


async def test_handle_gate_redirected_passes_none_when_no_prior_work():
    goal = _goal()
    gate_id = uuid4()
    gate = VerificationGate(
        id=gate_id,
        goal_id=goal.id,
        after_sequence=1,
        title="Checkpoint",
        status=GateStatus.AWAITING_APPROVAL,
    )
    store = _make_store(goal=goal, milestones=[], prior_work=[])
    store.get_gate = AsyncMock(return_value=gate)

    planner = AsyncMock()
    planner.replan_remaining = AsyncMock(return_value=([], []))

    executor, _, _, _ = _make_executor(store=store, planner=planner)
    await executor.handle_gate_redirected(gate_id, "feedback")

    call_kwargs = planner.replan_remaining.call_args.kwargs
    assert call_kwargs.get("prior_work") is None


# ── _promote_learnings ────────────────────────────────────────────────────────

from ze_memory.types import Fact
from ze_personal.goals.types import GoalLearning


def _learning(content="User prefers concise summaries.") -> GoalLearning:
    return GoalLearning(goal_id=uuid4(), content=content, source="milestone")


_USE_DEFAULT_MEMORY = object()  # sentinel to distinguish "no memory" from "use a fresh mock"


def _make_executor_with_memory(*, memory=_USE_DEFAULT_MEMORY, planner=None, store=None):
    store = store or _make_store()
    planner = planner or AsyncMock()
    if not hasattr(planner, "synthesize_retrospective") or not isinstance(
        planner.synthesize_retrospective, AsyncMock
    ):
        planner.synthesize_retrospective = AsyncMock(return_value="Goal done.")
    memory_store = AsyncMock() if memory is _USE_DEFAULT_MEMORY else memory
    push = AsyncMock()
    agent_getter = MagicMock(return_value=AsyncMock())
    from ze_personal.goals.executor import GoalExecutor
    executor = GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=agent_getter,
        memory_store=memory_store,
    )
    return executor, store, planner, memory_store


async def test_promote_learnings_skips_when_memory_is_none():
    executor, _, planner, _ = _make_executor_with_memory(memory=None)
    await executor._promote_learnings(_goal(), [_learning()])
    planner.promote_learnings.assert_not_called()


async def test_promote_learnings_skips_when_no_learnings():
    executor, _, planner, memory = _make_executor_with_memory()
    await executor._promote_learnings(_goal(), [])
    planner.promote_learnings.assert_not_called()
    memory.propose_facts.assert_not_called()


async def test_promote_learnings_calls_propose_facts_on_happy_path():
    fact = Fact(predicate="style", value="prefers bullets")
    planner = AsyncMock()
    planner.promote_learnings = AsyncMock(return_value=[fact])
    executor, _, _, memory = _make_executor_with_memory(planner=planner)

    await executor._promote_learnings(_goal(), [_learning()])

    memory.propose_facts.assert_called_once_with([fact])


async def test_promote_learnings_logs_count_on_success():
    import structlog.testing
    fact = Fact(predicate="k", value="v")
    planner = AsyncMock()
    planner.promote_learnings = AsyncMock(return_value=[fact])
    executor, _, _, _ = _make_executor_with_memory(planner=planner)

    with structlog.testing.capture_logs() as logs:
        await executor._promote_learnings(_goal(), [_learning()])

    assert any(l.get("event") == "goal_learning_promoted" for l in logs)


async def test_promote_learnings_logs_none_when_no_facts_returned():
    import structlog.testing
    planner = AsyncMock()
    planner.promote_learnings = AsyncMock(return_value=[])
    executor, _, _, _ = _make_executor_with_memory(planner=planner)

    with structlog.testing.capture_logs() as logs:
        await executor._promote_learnings(_goal(), [_learning()])

    assert any(l.get("event") == "goal_learning_promotion_none" for l in logs)


async def test_promote_learnings_swallows_planner_exception():
    import structlog.testing
    planner = AsyncMock()
    planner.promote_learnings = AsyncMock(side_effect=RuntimeError("LLM error"))
    executor, _, _, memory = _make_executor_with_memory(planner=planner)

    with structlog.testing.capture_logs() as logs:
        await executor._promote_learnings(_goal(), [_learning()])

    assert any(l.get("event") == "goal_learning_promotion_failed" for l in logs)
    memory.propose_facts.assert_not_called()


async def test_promote_learnings_swallows_propose_facts_exception():
    import structlog.testing
    fact = Fact(predicate="k", value="v")
    planner = AsyncMock()
    planner.promote_learnings = AsyncMock(return_value=[fact])
    memory = AsyncMock()
    memory.propose_facts = AsyncMock(side_effect=RuntimeError("DB error"))
    executor, _, _, _ = _make_executor_with_memory(planner=planner, memory=memory)

    with structlog.testing.capture_logs() as logs:
        await executor._promote_learnings(_goal(), [_learning()])

    assert any(l.get("event") == "goal_learning_promotion_write_failed" for l in logs)


async def test_push_retrospective_fires_promote_learnings_as_task():
    learnings = [_learning(content="Unique content XYZ")]
    store = _make_store()
    store.list_milestones = AsyncMock(return_value=[])
    store.list_learnings = AsyncMock(return_value=learnings)
    store.save_retrospective = AsyncMock()

    planner = AsyncMock()
    planner.synthesize_retrospective = AsyncMock(return_value="Done.")
    planner.promote_learnings = AsyncMock(return_value=[])

    executor, _, _, memory = _make_executor_with_memory(store=store, planner=planner)
    goal = _goal()

    await executor._push_retrospective(goal, goal.id)

    import asyncio
    await asyncio.sleep(0)

    planner.promote_learnings.assert_called_once()
    call_goal, call_learnings = planner.promote_learnings.call_args.args
    assert call_goal.title == goal.title
    assert len(call_learnings) == 1
    assert call_learnings[0].content == "Unique content XYZ"


async def test_executor_without_memory_store_passes_existing_tests():
    executor, store, planner, _ = _make_executor()
    assert executor._memory is None
