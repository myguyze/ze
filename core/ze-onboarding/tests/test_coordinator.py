from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from ze_onboarding import (
    CoreOnboardingProvider,
    OnboardingCoordinator,
    OnboardingSession,
    StoredOnboardingSeed,
    StoredOnboardingStep,
)


class FakeStore:
    def __init__(self) -> None:
        self.session: OnboardingSession | None = None
        self.steps: list[StoredOnboardingStep] = []
        self.seeds: list[StoredOnboardingSeed] = []
        self.completed = False

    async def get_active_session(self) -> OnboardingSession | None:
        return self.session if self.session is not None and self.session.status == "active" else None

    async def create_session(self) -> OnboardingSession:
        self.session = OnboardingSession(
            id=uuid4(),
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        return self.session

    async def complete_session(self, session_id: UUID) -> None:
        self.completed = True
        self.session = OnboardingSession(
            id=session_id,
            status="completed",
            started_at=self.session.started_at,
            completed_at=datetime.now(timezone.utc),
        )

    async def upsert_steps(self, session_id, steps) -> None:
        for idx, step in enumerate(steps):
            self.steps.append(
                StoredOnboardingStep(
                    id=uuid4(),
                    session_id=session_id,
                    plugin=step.plugin,
                    step_key=step.id,
                    status="active" if idx == 0 else "pending",
                    descriptor={
                        "id": step.id,
                        "plugin": step.plugin,
                        "title": step.title,
                        "kind": step.kind,
                        "description": step.description,
                        "fields": [
                            {
                                "id": field.id,
                                "label": field.label,
                                "field_type": field.field_type,
                                "placeholder": field.placeholder,
                                "options": field.options,
                                "required": field.required,
                                "help_text": field.help_text,
                            }
                            for field in step.fields
                        ],
                        "choices": [],
                    },
                )
            )

    async def get_current_step(self, session_id) -> StoredOnboardingStep | None:
        return next((s for s in self.steps if s.status == "active"), None)

    async def get_step_by_key(self, session_id, step_key) -> StoredOnboardingStep | None:
        return next((s for s in self.steps if s.step_key == step_key), None)

    async def complete_step(self, step, submission) -> None:
        self.steps = [
            StoredOnboardingStep(
                id=s.id,
                session_id=s.session_id,
                plugin=s.plugin,
                step_key=s.step_key,
                status="completed" if s.id == step.id else s.status,
                descriptor=s.descriptor,
                submission=submission if s.id == step.id else s.submission,
                completed_at=datetime.now(timezone.utc) if s.id == step.id else s.completed_at,
            )
            for s in self.steps
        ]

    async def insert_steps_after_current(self, session_id, steps) -> None:
        assert steps == []

    async def insert_seeds(self, session_id, step_id, seeds) -> None:
        for seed in seeds:
            self.seeds.append(
                StoredOnboardingSeed(
                    id=uuid4(),
                    session_id=session_id,
                    step_id=step_id,
                    plugin=seed.plugin,
                    kind=seed.kind,
                    key=seed.key,
                    value=seed.value,
                    confidence=seed.confidence,
                    review_status="pending",
                )
            )

    async def list_pending_seeds(self, session_id):
        return [s for s in self.seeds if s.review_status == "pending"]

    async def approve_pending_seeds(self, session_id) -> None:
        self.seeds = [
            StoredOnboardingSeed(
                id=s.id,
                session_id=s.session_id,
                step_id=s.step_id,
                plugin=s.plugin,
                kind=s.kind,
                key=s.key,
                value=s.value,
                confidence=s.confidence,
                review_status="approved" if s.review_status == "pending" else s.review_status,
            )
            for s in self.seeds
        ]

    async def list_approved_seeds(self, session_id):
        return [s for s in self.seeds if s.review_status == "approved"]

    async def mark_seeds_applied(self, seed_ids) -> None:
        self.seeds = [
            StoredOnboardingSeed(
                id=s.id,
                session_id=s.session_id,
                step_id=s.step_id,
                plugin=s.plugin,
                kind=s.kind,
                key=s.key,
                value=s.value,
                confidence=s.confidence,
                review_status="applied" if s.id in seed_ids else s.review_status,
            )
            for s in self.seeds
        ]


class FakePersistence:
    def __init__(self) -> None:
        self.applied: list[StoredOnboardingSeed] = []

    async def apply(self, seeds):
        self.applied.extend(seeds)
        return seeds


async def test_onboarding_start_returns_core_form():
    store = FakeStore()
    persistence = FakePersistence()
    coordinator = OnboardingCoordinator(
        providers=[CoreOnboardingProvider()],
        store=store,
        persistence=persistence,
    )

    view = await coordinator.start()

    assert view.completed is False
    assert view.components[0]["type"] == "form"
    assert view.components[0]["id"] == "core.profile"


async def test_onboarding_submit_reviews_then_applies_seed():
    store = FakeStore()
    persistence = FakePersistence()
    coordinator = OnboardingCoordinator(
        providers=[CoreOnboardingProvider()],
        store=store,
        persistence=persistence,
    )
    view = await coordinator.start()

    review = await coordinator.submit(
        session_id=view.session_id,
        step_id="core.profile",
        values={"preferred_name": "Joao", "timezone": "Europe/Lisbon"},
    )

    assert review.components[0]["type"] == "list"
    assert {item["text"] for item in review.components[0]["items"]} == {
        "preferred_name",
        "timezone",
    }

    done = await coordinator.submit(
        session_id=view.session_id,
        step_id="onboarding.review",
        values={"action": "approve"},
    )

    assert done.completed is True
    assert store.completed is True
    assert [seed.key for seed in persistence.applied] == ["preferred_name", "timezone"]
