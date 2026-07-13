from __future__ import annotations

from ze_sdk.onboarding import (
    OnboardingField,
    OnboardingResult,
    OnboardingSeed,
    OnboardingStep,
    OnboardingSubmission,
)


class PersonalOnboardingProvider:
    plugin_name = "ze_personal"
    priority = 10

    async def steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                id="ze_personal.preferences",
                plugin=self.plugin_name,
                title="Set your assistant style",
                kind="form",
                description="These preferences help Ze sound useful from the first conversation.",
                fields=[
                    OnboardingField(
                        id="communication_style",
                        label="How should Ze communicate?",
                        field_type="select",
                        options=["direct", "warm", "detailed", "brief"],
                    ),
                    OnboardingField(
                        id="current_goals",
                        label="Current goals Ze should know about",
                        field_type="textarea",
                        required=False,
                        placeholder="Ship Ze onboarding, improve Portuguese, ...",
                    ),
                    OnboardingField(
                        id="important_people",
                        label="Important people or organizations",
                        field_type="textarea",
                        required=False,
                        placeholder="Names, roles, and what Ze should remember",
                    ),
                ],
            )
        ]

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        communication_style = str(
            submission.values.get("communication_style") or ""
        ).strip()
        current_goals = str(submission.values.get("current_goals") or "").strip()
        important_people = str(submission.values.get("important_people") or "").strip()

        seeds: list[OnboardingSeed] = []
        if communication_style:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="communication_style",
                    value=communication_style,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )
        if current_goals:
            seeds.append(
                OnboardingSeed(
                    kind="memory_fact",
                    key="current_goals",
                    value=current_goals,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )
        if important_people:
            seeds.append(
                OnboardingSeed(
                    kind="memory_fact",
                    key="important_people",
                    value=important_people,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )

        return OnboardingResult(seeds=seeds)
