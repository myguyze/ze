from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_agents.errors import OnboardingError as OnboardingError  # noqa: F401 — re-export
from ze_onboarding.types import (
    OnboardingPersistence,
    OnboardingProvider,
    OnboardingStore,
    OnboardingSubmission,
    OnboardingView,
    StoredOnboardingSeed,
)

_REVIEW_STEP_ID = "onboarding.review"
_REVIEW_COMPONENT_ID = "onboarding.review"


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

    async def start_if_needed(self) -> OnboardingView | None:
        if await self._store.has_completed_session():
            return None
        return await self.start()

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
            if action == "approve":
                await self._store.approve_pending_seeds(session_id)
            elif action in {"edit", "reject"}:
                await self._store.reset_for_edit(session_id)
            else:
                raise OnboardingError(f"Unsupported onboarding review action: {action}")
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
            "description": descriptor.get("description"),
            "fields": descriptor.get("fields", []),
        }
    if kind == "choice":
        return {
            "type": "choice_group",
            "id": descriptor["id"],
            "title": descriptor["title"],
            "description": descriptor.get("description"),
            "options": descriptor.get("choices", []),
            "allow_multiple": descriptor.get("allow_multiple", False),
        }
    if kind == "consent":
        return {
            "type": "consent",
            "id": descriptor["id"],
            "title": descriptor["title"],
            "body": descriptor.get("description") or "",
            "scopes": descriptor.get("choices", []),
        }
    if kind == "connect_account":
        return {
            "type": "connect_account",
            "id": descriptor["id"],
            "provider": descriptor.get("plugin", "account"),
            "title": descriptor["title"],
            "description": descriptor.get("description") or "",
            "status": "not_connected",
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
            "id": str(seed.id),
            "label": seed.key.replace("_", " ").title(),
            "value": _format_seed_value(seed.value),
            "kind": seed.kind,
            "plugin": seed.plugin,
        }
        for seed in seeds
    ]
    return OnboardingView(
        session_id=session_id,
        text="Review what Ze will remember before saving it.",
        components=[
            {
                "type": "review",
                "id": _REVIEW_COMPONENT_ID,
                "title": "What Ze will remember",
                "items": items,
                "approve_label": "Save",
                "reject_label": "Edit",
            },
        ],
    )


def _format_seed_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        return ", ".join(f"{key}: {val}" for key, val in value.items())
    return str(value)
