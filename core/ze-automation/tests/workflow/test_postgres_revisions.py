from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ze_agents.errors import WorkflowPlanError
from ze_automation.workflow.postgres import PostgresWorkflowStore, _step_to_dict
from ze_automation.workflow.types import (
    ActorContext,
    ActorSource,
    Workflow,
    WorkflowStep,
)


class FakeConn:
    def __init__(self):
        self.workflows: dict = {}
        self.revisions: list[dict] = []
        self._next_rev_id = 1

    def transaction(self):
        @asynccontextmanager
        async def _txn():
            yield

        return _txn()

    async def fetchrow(self, query: str, *args):
        if "INSERT INTO workflows" in query:
            workflow_id = uuid4()
            name, description, steps, schedule, enabled, next_run_at = args
            self.workflows[workflow_id] = {"steps": steps}
            return {"id": workflow_id}
        if "SELECT steps FROM workflows" in query:
            workflow_id = args[0]
            wf = self.workflows.get(workflow_id)
            if wf is None:
                return None
            return {"steps": wf["steps"]}
        if "COALESCE(MAX(revision_number)" in query:
            workflow_id = args[0]
            existing = [
                r["revision_number"]
                for r in self.revisions
                if r["workflow_id"] == workflow_id
            ]
            return {"next": (max(existing) + 1) if existing else 1}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def execute(self, query: str, *args):
        if "UPDATE workflows" in query:
            steps, workflow_id = args
            self.workflows[workflow_id]["steps"] = steps
            return "UPDATE 1"
        if "INSERT INTO workflow_revisions" in query:
            if "VALUES ($1, 1, 'created'" in query:
                (
                    workflow_id,
                    steps_after,
                    summary,
                    actor_source,
                    session_id,
                    user_message_id,
                ) = args
                revision_number = 1
                steps_before = []
            else:
                (
                    workflow_id,
                    revision_number,
                    steps_before,
                    steps_after,
                    summary,
                    actor_source,
                    session_id,
                    user_message_id,
                ) = args
            self.revisions.append(
                {
                    "id": uuid4(),
                    "workflow_id": workflow_id,
                    "revision_number": revision_number,
                    "change_type": "created"
                    if revision_number == 1 and not steps_before
                    else "edited",
                    "steps_before": steps_before,
                    "steps_after": steps_after,
                    "summary": summary,
                    "actor_source": actor_source,
                    "actor_session_id": session_id,
                    "actor_user_message_id": user_message_id,
                    "created_at": None,
                }
            )
            return "INSERT 1"
        raise AssertionError(f"unexpected execute query: {query}")

    async def fetch(self, query: str, *args):
        workflow_id = args[0]
        rows = [r for r in self.revisions if r["workflow_id"] == workflow_id]
        rows.sort(key=lambda r: r["revision_number"], reverse=True)
        return rows


def _make_store():
    conn = FakeConn()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return PostgresWorkflowStore(pool), conn


def _workflow(steps=None) -> Workflow:
    return Workflow(
        id=uuid4(),
        name="wf",
        description="desc",
        steps=steps or [WorkflowStep(task="t1", id="s1")],
        schedule=None,
        enabled=True,
        last_run_at=None,
        next_run_at=None,
        created_at=None,
        updated_at=None,
    )


async def test_create_writes_created_revision():
    store, conn = _make_store()
    actor = ActorContext(
        source=ActorSource.AGENT, session_id="sess1", user_message_id=None
    )

    workflow_id = await store.create(_workflow(), actor=actor)

    assert len(conn.revisions) == 1
    rev = conn.revisions[0]
    assert rev["workflow_id"] == workflow_id
    assert rev["revision_number"] == 1
    assert rev["steps_before"] == []
    assert rev["actor_source"] == "agent"
    assert rev["actor_session_id"] == "sess1"


async def test_update_steps_writes_edited_revision():
    store, conn = _make_store()
    workflow_id = await store.create(_workflow())

    new_steps = [WorkflowStep(task="t1-changed", id="s1")]
    await store.update_steps(
        workflow_id, new_steps, actor=ActorContext(source=ActorSource.API)
    )

    assert len(conn.revisions) == 2
    rev2 = conn.revisions[1]
    assert rev2["revision_number"] == 2
    assert rev2["steps_after"] == [_step_to_dict(s) for s in new_steps]
    assert rev2["steps_before"] == [_step_to_dict(s) for s in _workflow().steps]


async def test_revision_one_immutable_after_revision_two():
    store, conn = _make_store()
    workflow_id = await store.create(_workflow())
    before_snapshot = dict(conn.revisions[0])

    await store.update_steps(workflow_id, [WorkflowStep(task="changed", id="s1")])

    revisions = await store.list_revisions(workflow_id)
    rev1 = next(r for r in revisions if r.revision_number == 1)
    assert rev1.steps_before == []
    assert [_step_to_dict(s) for s in rev1.steps_after] == before_snapshot[
        "steps_after"
    ]


async def test_update_steps_no_revision_on_noop():
    store, conn = _make_store()
    workflow_id = await store.create(_workflow())

    await store.update_steps(workflow_id, [WorkflowStep(task="t1", id="s1")])

    assert len(conn.revisions) == 1


async def test_update_steps_no_revision_on_validation_failure():
    store, conn = _make_store()
    workflow_id = await store.create(_workflow())

    dup_steps = [
        WorkflowStep(task="a", id="dup"),
        WorkflowStep(task="b", id="dup"),
    ]
    with pytest.raises(WorkflowPlanError):
        await store.update_steps(workflow_id, dup_steps)

    assert len(conn.revisions) == 1


async def test_list_revisions_returns_newest_first():
    store, conn = _make_store()
    workflow_id = await store.create(_workflow())
    await store.update_steps(workflow_id, [WorkflowStep(task="v2", id="s1")])
    await store.update_steps(workflow_id, [WorkflowStep(task="v3", id="s1")])

    revisions = await store.list_revisions(workflow_id)

    assert [r.revision_number for r in revisions] == [3, 2, 1]
