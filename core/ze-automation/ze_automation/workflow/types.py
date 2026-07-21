from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


@dataclass
class Branch:
    condition: str
    to: str


@dataclass
class WorkflowStep:
    task: str
    agent_hint: str | None = None
    verify: str | None = None
    intent: str = "execute"
    id: str = ""
    branches: list["Branch"] = field(default_factory=list)
    default_next: str | None = None
    on_failure: str = "fail"


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
    step_id: str = ""
    branch_taken: str | None = None
    attempt_count: int = 1
    no_results: bool = False


@dataclass
class WorkflowExecution:
    id: UUID
    workflow_id: UUID | None
    status: str
    step_results: list[StepResult] = field(default_factory=list)
    steps_snapshot: list[WorkflowStep] = field(default_factory=list)
    error: str | None = None
    summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class ActorSource(str, Enum):
    AGENT = "agent"
    API = "api"
    SYSTEM = "system"


@dataclass
class ActorContext:
    source: ActorSource
    session_id: str | None = None
    user_message_id: str | None = None


@dataclass
class WorkflowRevision:
    id: UUID
    workflow_id: UUID
    revision_number: int
    change_type: str
    steps_before: list[WorkflowStep]
    steps_after: list[WorkflowStep]
    summary: str
    actor: ActorContext
    created_at: datetime
