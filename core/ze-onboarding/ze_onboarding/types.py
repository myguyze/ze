from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

OnboardingStepKind = Literal[
    "intro",
    "form",
    "choice",
    "consent",
    "connect_account",
    "review",
]

SeedKind = Literal[
    "memory_fact",
    "profile_facet",
    "plugin_setting",
    "capability_request",
    "contact",
    "channel_connection",
]

OnboardingSessionStatus = Literal["active", "completed", "cancelled"]
OnboardingStoredStepStatus = Literal["pending", "active", "completed", "skipped"]
OnboardingSeedReviewStatus = Literal["pending", "approved", "rejected", "applied"]
ResetScope = Literal["memory", "personal_state", "full_dev"]


@dataclass(frozen=True)
class OnboardingField:
    id: str
    label: str
    field_type: Literal[
        "text",
        "textarea",
        "number",
        "date",
        "select",
        "multiselect",
        "boolean",
        "chips",
    ] = "text"
    required: bool = True
    placeholder: str | None = None
    options: list[str] | None = None
    help_text: str | None = None


@dataclass(frozen=True)
class OnboardingChoice:
    id: str
    label: str
    description: str | None = None
    recommended: bool = False


@dataclass(frozen=True)
class OnboardingStep:
    id: str
    plugin: str
    title: str
    kind: OnboardingStepKind
    description: str | None = None
    fields: list[OnboardingField] = field(default_factory=list)
    choices: list[OnboardingChoice] = field(default_factory=list)
    allow_multiple: bool = False
    required: bool = True
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OnboardingSubmission:
    step_id: str
    values: dict[str, Any]


@dataclass(frozen=True)
class OnboardingSeed:
    kind: SeedKind
    key: str
    value: Any
    confidence: float = 1.0
    source_step_id: str | None = None
    plugin: str | None = None
    review_required: bool = True


@dataclass(frozen=True)
class OnboardingResult:
    seeds: list[OnboardingSeed] = field(default_factory=list)
    next_steps: list[OnboardingStep] = field(default_factory=list)
    complete: bool = False


class OnboardingProvider(Protocol):
    plugin_name: str
    priority: int

    async def steps(self) -> list[OnboardingStep]:
        """Return this plugin's initial onboarding steps."""

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        """Validate one submission and return typed seeds or follow-up steps."""


@dataclass(frozen=True)
class OnboardingSession:
    id: UUID
    status: OnboardingSessionStatus
    started_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True)
class StoredOnboardingStep:
    id: UUID
    session_id: UUID
    plugin: str
    step_key: str
    status: OnboardingStoredStepStatus
    descriptor: dict[str, Any]
    submission: dict[str, Any] | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class StoredOnboardingSeed:
    id: UUID
    session_id: UUID
    step_id: UUID | None
    plugin: str | None
    kind: str
    key: str
    value: Any
    confidence: float
    review_status: OnboardingSeedReviewStatus


@dataclass(frozen=True)
class OnboardingView:
    session_id: UUID
    text: str
    components: list[dict[str, Any]] = field(default_factory=list)
    completed: bool = False


@dataclass(frozen=True)
class ResetPreview:
    scope: ResetScope
    counts: dict[str, int]


@dataclass(frozen=True)
class ResetResult:
    scope: ResetScope
    deleted: dict[str, int]


class OnboardingStore(Protocol):
    async def get_active_session(self) -> OnboardingSession | None: ...
    async def has_completed_session(self) -> bool: ...
    async def create_session(self) -> OnboardingSession: ...
    async def complete_session(self, session_id: UUID) -> None: ...
    async def upsert_steps(self, session_id: UUID, steps: list[OnboardingStep]) -> None: ...
    async def get_current_step(self, session_id: UUID) -> StoredOnboardingStep | None: ...
    async def get_step_by_key(
        self,
        session_id: UUID,
        step_key: str,
    ) -> StoredOnboardingStep | None: ...
    async def complete_step(
        self,
        step: StoredOnboardingStep,
        submission: dict[str, Any],
    ) -> None: ...
    async def insert_steps_after_current(
        self,
        session_id: UUID,
        steps: list[OnboardingStep],
    ) -> None: ...
    async def insert_seeds(
        self,
        session_id: UUID,
        step_id: UUID | None,
        seeds: list[OnboardingSeed],
    ) -> None: ...
    async def list_pending_seeds(self, session_id: UUID) -> list[StoredOnboardingSeed]: ...
    async def approve_pending_seeds(self, session_id: UUID) -> None: ...
    async def reset_for_edit(self, session_id: UUID) -> None: ...
    async def list_approved_seeds(self, session_id: UUID) -> list[StoredOnboardingSeed]: ...
    async def mark_seeds_applied(self, seed_ids: list[UUID]) -> None: ...


class OnboardingPersistence(Protocol):
    async def apply(self, seeds: list[StoredOnboardingSeed]) -> list[StoredOnboardingSeed]: ...
