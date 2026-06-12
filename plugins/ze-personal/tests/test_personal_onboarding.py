from ze_personal.onboarding import PersonalOnboardingProvider
from ze_sdk.onboarding import OnboardingSubmission


async def test_personal_onboarding_provider_returns_reviewable_seeds():
    provider = PersonalOnboardingProvider()

    steps = await provider.steps()
    result = await provider.handle_submission(
        OnboardingSubmission(
            step_id=steps[0].id,
            values={
                "communication_style": "direct",
                "current_goals": "Finish onboarding",
                "important_people": "Ana is my accountant",
            },
        )
    )

    assert steps[0].id == "ze_personal.preferences"
    assert [(seed.kind, seed.key, seed.value) for seed in result.seeds] == [
        ("profile_facet", "communication_style", "direct"),
        ("memory_fact", "current_goals", "Finish onboarding"),
        ("memory_fact", "important_people", "Ana is my accountant"),
    ]
