from ze_news.onboarding import NewsOnboardingProvider
from ze_sdk.onboarding import OnboardingSubmission


async def test_news_onboarding_provider_returns_preference_seeds():
    provider = NewsOnboardingProvider()

    steps = await provider.steps()
    result = await provider.handle_submission(
        OnboardingSubmission(
            step_id=steps[0].id,
            values={
                "topics": ["AI", "Portugal"],
                "excluded_topics": "celebrity news, sports",
                "source_languages": ["English"],
            },
        )
    )

    assert steps[0].id == "ze_news.preferences"
    assert [(seed.kind, seed.key, seed.value) for seed in result.seeds] == [
        ("profile_facet", "news_interests", ["AI", "Portugal"]),
        ("profile_facet", "news_exclusions", ["celebrity news", "sports"]),
        ("profile_facet", "news_source_languages", ["English"]),
    ]
