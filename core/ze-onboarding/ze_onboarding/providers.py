from __future__ import annotations

from ze_onboarding.types import (
    OnboardingField,
    OnboardingResult,
    OnboardingSeed,
    OnboardingStep,
    OnboardingSubmission,
)


class CoreOnboardingProvider:
    plugin_name = "core"
    priority = 0

    async def steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                id="core.profile",
                plugin=self.plugin_name,
                title="Tell Ze the basics",
                kind="form",
                description="This helps Ze address you correctly and schedule time-based work.",
                fields=[
                    OnboardingField(
                        id="preferred_name",
                        label="What should Ze call you?",
                        placeholder="Joao",
                    ),
                    OnboardingField(
                        id="timezone",
                        label="Primary timezone",
                        placeholder="Europe/Lisbon",
                    ),
                ],
            )
        ]

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        values = submission.values
        seeds: list[OnboardingSeed] = []
        preferred_name = str(values.get("preferred_name") or "").strip()
        timezone = str(values.get("timezone") or "").strip()

        if preferred_name:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="preferred_name",
                    value=preferred_name,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )
        if timezone:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="timezone",
                    value=timezone,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )

        return OnboardingResult(seeds=seeds)
