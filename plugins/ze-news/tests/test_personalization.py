from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ze_news.preferences import NewsPreferenceBuilder
from ze_news.store import NewsStore, _exclusion_term_patterns
from ze_news.types import Article, NewsPreference, PersonalizationContext


def _make_article(**kwargs) -> Article:
    defaults = dict(
        url="https://example.com/article",
        source_key="test",
        title="Test Headline",
        summary="A short summary about technology.",
        published_at=datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc),
        tags=["global"],
    )
    return Article(**{**defaults, **kwargs})


def _make_store(encode_return=None):
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    embedder = MagicMock()
    embedder.encode.return_value = encode_return or [0.1] * 384

    return NewsStore(pool=pool, embedder=embedder), conn


class _KeywordEmbedder:
    def encode(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            1.0 if "tech" in lowered or "ai" in lowered else 0.0,
            1.0 if "banana" in lowered or "fruit" in lowered else 0.0,
            1.0 if "econom" in lowered else 0.0,
        ]


# ── NewsPreferenceBuilder ────────────────────────────────────────────────────


async def test_preference_builder_includes_explicit_news_facts():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="news_interest",
                value="AI, economics",
                confidence=0.9,
                contradicted=False,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("what's in the news?")

    topics = [p.topic for p in ctx.preferences if p.polarity == "include"]
    assert "AI" in topics
    assert "economics" in topics


async def test_preference_builder_ignores_activity_facts():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="activity_programming",
                value="programming/coding the AI assistant",
                confidence=0.9,
                contradicted=False,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("what's in the news?")

    assert all("programming" not in p.topic for p in ctx.preferences)


async def test_preference_builder_extracts_exclusion_from_value():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="preference",
                value="don't show me bananas",
                confidence=0.9,
                contradicted=False,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("headlines")

    assert "bananas" in ctx.exclusions
    assert any(
        p.polarity == "exclude" and p.topic == "bananas" for p in ctx.preferences
    )


async def test_preference_builder_diagnostic_query_is_not_positive_interest():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(return_value=[])
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build(
        "why do you keep suggesting bananas?"
    )

    assert not any(
        p.source == "query" and "bananas" in p.topic for p in ctx.preferences
    )


async def test_preference_builder_ignores_low_confidence_facts():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="news_interest",
                value="AI",
                confidence=0.4,
                contradicted=False,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals, min_confidence=0.65).build(
        "headlines"
    )

    assert not any(p.source == "fact" and p.topic == "AI" for p in ctx.preferences)


async def test_preference_builder_ignores_contradicted_facts():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="news_interest",
                value="AI",
                confidence=0.9,
                contradicted=True,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("headlines")

    assert not any(p.source == "fact" for p in ctx.preferences)


async def test_preference_builder_goal_weight_lower_than_explicit_news():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(
        return_value=[
            SimpleNamespace(
                predicate="news_interest",
                value="AI",
                confidence=0.9,
                contradicted=False,
            ),
        ]
    )
    memory_store.get_profile = AsyncMock(return_value=[])
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=["Launch Ze"])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("headlines")

    fact_weight = next(p.weight for p in ctx.preferences if p.source == "fact")
    goal_weight = next(p.weight for p in ctx.preferences if p.source == "goal")
    assert fact_weight > goal_weight


async def test_preference_builder_includes_profile_and_goals():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(return_value=[])
    memory_store.get_profile = AsyncMock(
        return_value=[
            SimpleNamespace(key="topics", value="AI; startups", confidence=0.9),
        ]
    )
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=["Launch Ze"])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("headlines")

    assert any(p.source == "profile" and p.topic == "AI" for p in ctx.preferences)
    assert any(p.source == "goal" and p.topic == "Launch Ze" for p in ctx.preferences)


async def test_preference_builder_includes_onboarding_news_facets():
    memory_store = MagicMock()
    memory_store.list_recent_facts = AsyncMock(return_value=[])
    memory_store.get_profile = AsyncMock(
        return_value=[
            SimpleNamespace(key="news_interests", value="AI, Portugal", confidence=0.9),
            SimpleNamespace(key="news_exclusions", value="football", confidence=0.9),
        ]
    )
    goals = MagicMock()
    goals.list_active_goal_titles = AsyncMock(return_value=[])

    ctx = await NewsPreferenceBuilder(memory_store, goals).build("")

    assert any(p.source == "profile" and p.topic == "AI" for p in ctx.preferences)
    assert "football" in ctx.exclusions
    assert any(
        p.polarity == "exclude" and p.topic == "football" for p in ctx.preferences
    )


# ── PersonalizationContext ──────────────────────────────────────────────────


def test_personalization_context_defaults():
    ctx = PersonalizationContext(interest_text="tech AI")
    assert ctx.explore_ratio == 0.2
    assert ctx.exclusions == []
    assert ctx.fact_count == 0


def test_personalization_context_custom():
    ctx = PersonalizationContext(
        interest_text="sports football",
        exclusions=["football"],
        explore_ratio=0.3,
        fact_count=10,
    )
    assert ctx.exclusions == ["football"]
    assert ctx.explore_ratio == 0.3
    assert ctx.fact_count == 10


# ── _apply_exclusions ────────────────────────────────────────────────────────


def test_apply_exclusions_filters_by_title():
    store, _ = _make_store()
    articles = [
        _make_article(title="Football match results"),
        _make_article(title="Tech startup raises funding", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1
    assert result[0].title == "Tech startup raises funding"


def test_apply_exclusions_filters_by_summary():
    store, _ = _make_store()
    articles = [
        _make_article(summary="The match was about football tactics"),
        _make_article(summary="AI breakthroughs in 2026", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1
    assert "AI" in result[0].summary


def test_apply_exclusions_word_boundary():
    store, _ = _make_store()
    articles = [
        _make_article(title="New transport routes announced"),
        _make_article(
            title="Sport highlights of the week", url="https://example.com/2"
        ),
    ]
    # "sport" should NOT match "transport" due to word boundary, but SHOULD match "Sport highlights"
    result = store._apply_exclusions(articles, ["sport"])
    assert len(result) == 1
    assert "transport" in result[0].title


def test_apply_exclusions_empty_returns_all():
    store, _ = _make_store()
    articles = [_make_article(), _make_article(url="https://example.com/2")]
    result = store._apply_exclusions(articles, [])
    assert len(result) == 2


def test_apply_exclusions_case_insensitive():
    store, _ = _make_store()
    articles = [
        _make_article(title="FOOTBALL news today"),
        _make_article(title="Tech news", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["football"])
    assert len(result) == 1


def test_apply_exclusions_plural_term_matches_singular_title():
    store, _ = _make_store()
    articles = [
        _make_article(title="Banana harvest improves"),
        _make_article(title="Economy grows", url="https://example.com/2"),
    ]
    result = store._apply_exclusions(articles, ["bananas"])
    assert len(result) == 1
    assert result[0].title == "Economy grows"


def test_exclusion_patterns_do_not_match_substrings():
    patterns = _exclusion_term_patterns("sport")
    assert not any(p.search("New transport routes announced") for p in patterns)


# ── get_personalized fallback ────────────────────────────────────────────────


async def test_get_personalized_falls_back_when_empty_interest():
    store, conn = _make_store()
    conn.fetch.return_value = []

    ctx = PersonalizationContext(interest_text="", fact_count=10)
    relevant, discovery = await store.get_personalized(ctx, limit=5)

    assert discovery == []
    conn.fetch.assert_called_once()  # called get_recent


async def test_get_personalized_falls_back_below_min_facts():
    store, conn = _make_store()
    conn.fetch.return_value = []

    ctx = PersonalizationContext(interest_text="tech AI", fact_count=2)
    relevant, discovery = await store.get_personalized(ctx, limit=5, min_facts=5)

    assert discovery == []
    conn.fetch.assert_called_once()  # get_recent called


# ── get_personalized scoring ─────────────────────────────────────────────────


async def test_get_personalized_splits_into_buckets():
    store, conn = _make_store()

    articles = [
        _make_article(
            url=f"https://example.com/{i}",
            title=f"Article {i}",
            published_at=datetime(2026, 6, 7, 12, i, tzinfo=timezone.utc),
        )
        for i in range(10)
    ]

    def _make_row(a):
        row = MagicMock()
        row.__getitem__ = lambda self, k: getattr(a, k) if k != "tags" else a.tags
        return row

    conn.fetch.return_value = [_make_row(a) for a in articles]

    ctx = PersonalizationContext(interest_text="technology AI", fact_count=10)
    relevant, discovery = await store.get_personalized(ctx, limit=5, min_facts=5)

    assert len(relevant) + len(discovery) <= 5
    assert len(relevant) > 0


async def test_get_personalized_discovery_sorted_by_recency():
    store, conn = _make_store()

    t1 = datetime(2026, 6, 7, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 7, 11, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)

    articles = [
        _make_article(url="https://example.com/1", title="A1", published_at=t1),
        _make_article(url="https://example.com/2", title="A2", published_at=t2),
        _make_article(url="https://example.com/3", title="A3", published_at=t3),
        _make_article(url="https://example.com/4", title="A4", published_at=t1),
        _make_article(url="https://example.com/5", title="A5", published_at=t2),
        _make_article(url="https://example.com/6", title="A6", published_at=t3),
    ]

    def _make_row(a):
        row = MagicMock()
        row.__getitem__ = lambda self, k: getattr(a, k, []) if k != "tags" else a.tags
        return row

    conn.fetch.return_value = [_make_row(a) for a in articles]

    ctx = PersonalizationContext(
        interest_text="AI tech", fact_count=10, explore_ratio=0.5
    )
    relevant, discovery = await store.get_personalized(ctx, limit=4, min_facts=5)

    if discovery:
        times = [a.published_at for a in discovery]
        assert times == sorted(times, reverse=True)


async def test_get_personalized_query_relevance_outranks_stored_banana_interest():
    store, _ = _make_store()
    store._embedder = _KeywordEmbedder()
    store.get_recent = AsyncMock(
        return_value=[
            _make_article(
                url="https://example.com/bananas",
                title="Banana harvest improves",
                summary="A fruit industry update.",
                tags=["food"],
            ),
            _make_article(
                url="https://example.com/tech",
                title="AI startup launches new model",
                summary="Technology companies race ahead.",
                tags=["tech"],
            ),
        ]
    )
    ctx = PersonalizationContext(
        query_text="tech headlines",
        preferences=[
            NewsPreference(
                topic="bananas",
                polarity="include",
                source="fact",
                weight=0.9,
                reason="stored news preference: bananas",
            ),
            NewsPreference(
                topic="tech headlines",
                polarity="include",
                source="query",
                weight=1.0,
                reason="matches current request: tech headlines",
            ),
        ],
    )

    relevant, _ = await store.get_personalized(ctx, limit=2, min_facts=5)

    assert relevant[0].url == "https://example.com/tech"


async def test_get_personalized_filters_excluded_banana_topic():
    store, _ = _make_store()
    store._embedder = _KeywordEmbedder()
    store.get_recent = AsyncMock(
        return_value=[
            _make_article(
                url="https://example.com/bananas",
                title="Banana import news",
                summary="Fruit market update.",
                tags=["food"],
            ),
            _make_article(
                url="https://example.com/economy",
                title="Economy grows",
                summary="Economic indicators improved.",
                tags=["business"],
            ),
        ]
    )
    ctx = PersonalizationContext(
        query_text="headlines",
        exclusions=["bananas"],
        preferences=[
            NewsPreference(
                topic="bananas",
                polarity="exclude",
                source="fact",
                weight=1.0,
                reason="stored news exclusion: bananas",
            ),
            NewsPreference(
                topic="economy",
                polarity="include",
                source="fact",
                weight=0.9,
                reason="stored news preference: economy",
            ),
        ],
    )

    relevant, discovery = await store.get_personalized(ctx, limit=2, min_facts=1)

    assert all("Banana" not in article.title for article in relevant + discovery)


async def test_get_personalized_exclusion_only_context_filters_recent_fallback():
    store, _ = _make_store()
    store.get_recent = AsyncMock(
        return_value=[
            _make_article(url="https://example.com/1", title="Banana headline"),
            _make_article(url="https://example.com/2", title="Tech headline"),
        ]
    )
    ctx = PersonalizationContext(
        exclusions=["bananas"],
        preferences=[
            NewsPreference(
                topic="bananas",
                polarity="exclude",
                source="fact",
                weight=1.0,
                reason="stored news exclusion: bananas",
            ),
        ],
    )

    relevant, discovery = await store.get_personalized(ctx, limit=2, min_facts=5)

    assert [article.title for article in relevant] == ["Tech headline"]
    assert discovery == []


async def test_get_personalized_caps_repeated_topics():
    store, _ = _make_store()
    store._embedder = _KeywordEmbedder()
    store.get_recent = AsyncMock(
        return_value=[
            _make_article(url="https://example.com/1", title="AI one", tags=["tech"]),
            _make_article(url="https://example.com/2", title="AI two", tags=["tech"]),
            _make_article(url="https://example.com/3", title="AI three", tags=["tech"]),
            _make_article(
                url="https://example.com/4", title="Economy", tags=["business"]
            ),
        ]
    )
    ctx = PersonalizationContext(
        query_text="tech headlines",
        max_per_topic=2,
        preferences=[
            NewsPreference(
                topic="tech headlines",
                polarity="include",
                source="query",
                weight=1.0,
                reason="matches current request: tech headlines",
            ),
        ],
    )

    relevant, discovery = await store.get_personalized(ctx, limit=4, min_facts=5)
    tech_count = sum(1 for article in relevant + discovery if article.tags == ["tech"])

    assert tech_count == 2


# ── _score_articles ───────────────────────────────────────────────────────────


def test_score_articles_zero_vector_gives_zero():
    store, _ = _make_store()
    article = _make_article()
    store._embedder.encode.return_value = [0.0] * 384
    results = store._score_articles([article], [0.0] * 384)
    assert results[0][1] == 0.0


def test_score_articles_identical_vectors_give_one():
    store, _ = _make_store()
    vec = [0.1] * 384
    store._embedder.encode.return_value = vec
    article = _make_article()
    results = store._score_articles([article], vec)
    assert abs(results[0][1] - 1.0) < 1e-6
