from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_onboarding.types import (
    OnboardingPersistence,
    OnboardingProvider,
    OnboardingStore,
    OnboardingSubmission,
    OnboardingView,
    StoredOnboardingSeed,
)

_REVIEW_STEP_ID = "onboarding.review"


class OnboardingError(Exception):
    """Onboarding flow failed or received an invalid submission."""


class OnboardingCoordinator:
    def __init__(
        self,
        *,
        providers: list[OnboardingProvider],
        store: OnboardingStore,
        persistence: OnboardingPersistence,
    ) -> None:
        self._providers = sorted(providers, key=lambda p: (p.priority, p.plugin_name))
        self._providers_by_name = {p.plugin_name: p for p in self._providers}
        self._store = store
        self._persistence = persistence

    async def start(self) -> OnboardingView:
        session = await self._store.get_active_session()
        if session is None:
            session = await self._store.create_session()
            steps = []
            for provider in self._providers:
                steps.extend(await provider.steps())
            await self._store.upsert_steps(session.id, steps)
        return await self.get_current(session.id)

    async def get_current(self, session_id: UUID) -> OnboardingView:
        step = await self._store.get_current_step(session_id)
        if step is not None:
            return OnboardingView(
                session_id=session_id,
                text=step.descriptor.get("description") or step.descriptor.get("title") or "",
                components=[_descriptor_to_component(step.descriptor)],
            )

        pending = await self._store.list_pending_seeds(session_id)
        if pending:
            return _review_view(session_id, pending)

        approved = await self._store.list_approved_seeds(session_id)
        if approved:
            applied = await self._persistence.apply(approved)
            await self._store.mark_seeds_applied([seed.id for seed in applied])

        await self._store.complete_session(session_id)
        return OnboardingView(
            session_id=session_id,
            text="Onboarding is complete. Ze is ready.",
            components=[{
                "type": "card",
                "title": "Setup complete",
                "body": "Your starting preferences have been saved.",
                "style": "success",
            }],
            completed=True,
        )

    async def submit(
        self,
        *,
        session_id: UUID,
        step_id: str,
        values: dict[str, Any],
    ) -> OnboardingView:
        if step_id == _REVIEW_STEP_ID:
            action = str(values.get("action") or values.get("choice") or "approve")
            if action != "approve":
                raise OnboardingError("Only review approval is supported in this version")
            await self._store.approve_pending_seeds(session_id)
            return await self.get_current(session_id)

        step = await self._store.get_step_by_key(session_id, step_id)
        if step is None:
            raise OnboardingError(f"Unknown onboarding step: {step_id}")
        if step.status == "completed":
            return await self.get_current(session_id)

        provider = self._providers_by_name.get(step.plugin)
        if provider is None:
            raise OnboardingError(f"No onboarding provider registered for {step.plugin}")

        submission = OnboardingSubmission(step_id=step.step_key, values=values)
        result = await provider.handle_submission(submission)
        await self._store.complete_step(step, values)
        await self._store.insert_seeds(session_id, step.id, result.seeds)
        await self._store.insert_steps_after_current(session_id, result.next_steps)
        return await self.get_current(session_id)


def _descriptor_to_component(descriptor: dict[str, Any]) -> dict[str, Any]:
    kind = descriptor["kind"]
    if kind == "form":
        return {
            "type": "form",
            "id": descriptor["id"],
            "title": descriptor["title"],
            "fields": descriptor.get("fields", []),
        }
    if kind == "choice":
        return {
            "type": "confirm",
            "id": descriptor["id"],
            "prompt": descriptor["title"],
            "actions": [
                {"label": choice["label"], "value": choice["id"], "style": "secondary"}
                for choice in descriptor.get("choices", [])
            ],
        }
    if kind == "consent":
        return {
            "type": "confirm",
            "id": descriptor["id"],
            "prompt": descriptor["title"],
            "actions": [
                {"label": "Allow", "value": "approve", "style": "primary"},
                {"label": "Skip", "value": "skip", "style": "secondary"},
            ],
        }
    return {
        "type": "card",
        "id": descriptor["id"],
        "title": descriptor["title"],
        "body": descriptor.get("description") or "",
        "style": "info",
    }


def _review_view(session_id: UUID, seeds: list[StoredOnboardingSeed]) -> OnboardingView:
    items = [
        {
            "text": seed.key,
            "subtext": str(seed.value),
            "status": seed.kind,
        }
        for seed in seeds
    ]
    return OnboardingView(
        session_id=session_id,
        text="Review what Ze will remember before saving it.",
        components=[
            {
                "type": "list",
                "title": "What Ze will remember",
                "items": items,
            },
            {
                "type": "confirm",
                "id": _REVIEW_STEP_ID,
                "prompt": "Save these onboarding details?",
                "actions": [
                    {"label": "Save", "value": "approve", "style": "primary"},
                ],
            },
        ],
    )
