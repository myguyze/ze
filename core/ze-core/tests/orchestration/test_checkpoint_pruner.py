from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from ze_core.orchestration.checkpoint_pruner import CheckpointPruner


class _FakeConn:
    def __init__(self, db: dict) -> None:
        self._db = db

    async def fetch(self, query: str, *args):
        query = " ".join(query.split())
        if query.startswith("SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints"):
            seen = {(r["thread_id"], r["checkpoint_ns"]) for r in self._db["checkpoints"]}
            return [{"thread_id": t, "checkpoint_ns": ns} for t, ns in seen]
        if query.startswith("SELECT checkpoint_id, checkpoint FROM checkpoints"):
            thread_id, checkpoint_ns = args
            rows = [
                r
                for r in self._db["checkpoints"]
                if r["thread_id"] == thread_id and r["checkpoint_ns"] == checkpoint_ns
            ]
            return sorted(rows, key=lambda r: r["checkpoint_id"], reverse=True)
        if query.startswith("SELECT channel, version FROM checkpoint_blobs"):
            thread_id, checkpoint_ns = args
            return [
                r
                for r in self._db["checkpoint_blobs"]
                if r["thread_id"] == thread_id and r["checkpoint_ns"] == checkpoint_ns
            ]
        raise AssertionError(f"unexpected query: {query}")

    async def execute(self, query: str, *args) -> str:
        query = " ".join(query.split())
        if query.startswith("DELETE FROM checkpoint_writes"):
            thread_id, checkpoint_ns, ids = args
            before = len(self._db["checkpoint_writes"])
            self._db["checkpoint_writes"] = [
                r
                for r in self._db["checkpoint_writes"]
                if not (
                    r["thread_id"] == thread_id
                    and r["checkpoint_ns"] == checkpoint_ns
                    and r["checkpoint_id"] in ids
                )
            ]
            return f"DELETE {before - len(self._db['checkpoint_writes'])}"
        if query.startswith("DELETE FROM checkpoints"):
            thread_id, checkpoint_ns, ids = args
            before = len(self._db["checkpoints"])
            self._db["checkpoints"] = [
                r
                for r in self._db["checkpoints"]
                if not (
                    r["thread_id"] == thread_id
                    and r["checkpoint_ns"] == checkpoint_ns
                    and r["checkpoint_id"] in ids
                )
            ]
            return f"DELETE {before - len(self._db['checkpoints'])}"
        raise AssertionError(f"unexpected query: {query}")

    async def executemany(self, query: str, args_list) -> None:
        query = " ".join(query.split())
        assert query.startswith("DELETE FROM checkpoint_blobs")
        to_delete = set(args_list)
        self._db["checkpoint_blobs"] = [
            r
            for r in self._db["checkpoint_blobs"]
            if (r["thread_id"], r["checkpoint_ns"], r["channel"], r["version"]) not in to_delete
        ]

    @asynccontextmanager
    async def transaction(self):
        yield


class _FakePool:
    def __init__(self, db: dict) -> None:
        self._conn = _FakeConn(db)

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def _checkpoint(thread_id, ns, cp_id, versions):
    return {
        "thread_id": thread_id,
        "checkpoint_ns": ns,
        "checkpoint_id": cp_id,
        "checkpoint": {"channel_versions": versions},
    }


@pytest.mark.asyncio
async def test_prune_keeps_most_recent_n_and_drops_rest():
    db = {
        "checkpoints": [
            _checkpoint("t1", "", "0001", {"messages": "1"}),
            _checkpoint("t1", "", "0002", {"messages": "2"}),
            _checkpoint("t1", "", "0003", {"messages": "3"}),
            _checkpoint("t1", "", "0004", {"messages": "4"}),
        ],
        "checkpoint_writes": [
            {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "0001"},
            {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "0004"},
        ],
        "checkpoint_blobs": [
            {"thread_id": "t1", "checkpoint_ns": "", "channel": "messages", "version": "1"},
            {"thread_id": "t1", "checkpoint_ns": "", "channel": "messages", "version": "4"},
        ],
    }
    pool = _FakePool(db)
    pruner = CheckpointPruner(pool=pool, keep_per_thread=2)

    await pruner.run()

    remaining_ids = {r["checkpoint_id"] for r in db["checkpoints"]}
    assert remaining_ids == {"0003", "0004"}
    assert db["checkpoint_writes"] == [
        {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "0004"},
    ]
    assert db["checkpoint_blobs"] == [
        {"thread_id": "t1", "checkpoint_ns": "", "channel": "messages", "version": "4"},
    ]


@pytest.mark.asyncio
async def test_prune_noop_when_under_threshold():
    db = {
        "checkpoints": [
            _checkpoint("t1", "", "0001", {"messages": "1"}),
        ],
        "checkpoint_writes": [],
        "checkpoint_blobs": [],
    }
    pool = _FakePool(db)
    pruner = CheckpointPruner(pool=pool, keep_per_thread=3)

    await pruner.run()

    assert len(db["checkpoints"]) == 1
