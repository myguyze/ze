from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class WorkflowStep:
    task: str
    agent_hint: str | None = None
    verify: str | None = None
    intent: str = "execute"


@dataclass
class Workflow:
    id: UUID
    name: str
    description: str
    steps: list[WorkflowStep]
    schedule: str | None
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class StepResult:
    step_index: int
    task: str
    output: str
    success: bool
    error: str | None
    duration_ms: int


@dataclass
class WorkflowExecution:
    id: UUID
    workflow_id: UUID | None
    status: str
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
