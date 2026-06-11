from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ze_personal.workflow.types import StepResult, Workflow, WorkflowExecution


class WorkflowStore(Protocol):
    async def create(self, workflow: Workflow) -> UUID: ...

    async def get(self, workflow_id: UUID) -> Workflow | None: ...

    async def get_by_name(self, name: str) -> Workflow | None: ...

    async def list_all(self) -> list[Workflow]: ...

    async def list_enabled_scheduled(self) -> list[Workflow]: ...

    async def set_enabled(self, workflow_id: UUID, enabled: bool) -> None: ...

    async def delete(self, workflow_id: UUID) -> None: ...

    async def update_run_timestamps(
        self,
        workflow_id: UUID,
        last_run_at: datetime,
        next_run_at: datetime | None,
    ) -> None: ...

    async def start_execution(self, workflow_id: UUID | None) -> UUID: ...

    async def record_step(self, execution_id: UUID, result: StepResult) -> None: ...

    async def finish_execution(
        self,
        execution_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None: ...

    async def list_executions(self, workflow_id: UUID, limit: int = 20) -> list[WorkflowExecution]: ...
