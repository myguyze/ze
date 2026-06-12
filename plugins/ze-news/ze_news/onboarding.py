from __future__ import annotations

from typing import Any

from ze_sdk.onboarding import (
    OnboardingField,
    OnboardingResult,
    OnboardingSeed,
    OnboardingStep,
    OnboardingSubmission,
)


class NewsOnboardingProvider:
    plugin_name = "ze_news"
    priority = 20

    async def steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                id="ze_news.preferences",
                plugin=self.plugin_name,
                title="Tune your news",
                kind="form",
                description="Give Ze a starting point for what to include and avoid in news digests.",
                fields=[
                    OnboardingField(
                        id="topics",
                        label="Topics you care about",
                        field_type="chips",
                        placeholder="AI, Portugal, markets",
                    ),
                    OnboardingField(
                        id="excluded_topics",
                        label="Topics to avoid",
                        field_type="chips",
                        required=False,
                        placeholder="celebrity news, sports",
                    ),
                    OnboardingField(
                        id="source_languages",
                        label="Preferred source languages",
                        field_type="chips",
                        required=False,
                        placeholder="English, Portuguese",
                    ),
                ],
            )
        ]

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        topics = _string_list(submission.values.get("topics"))
        excluded_topics = _string_list(submission.values.get("excluded_topics"))
        source_languages = _string_list(submission.values.get("source_languages"))

        seeds: list[OnboardingSeed] = []
        if topics:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="news_interests",
                    value=topics,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )
        if excluded_topics:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="news_exclusions",
                    value=excluded_topics,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )
        if source_languages:
            seeds.append(
                OnboardingSeed(
                    kind="profile_facet",
                    key="news_source_languages",
                    value=source_languages,
                    plugin=self.plugin_name,
                    source_step_id=submission.step_id,
                )
            )

        return OnboardingResult(seeds=seeds)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in raw if str(item).strip()]
