from ze_agents.progress.translations import ProgressTranslations


def make_translations(data: dict, fallback: dict | None = None) -> ProgressTranslations:
    return ProgressTranslations(data=data, fallback=fallback or data)


class TestResolve:
    def test_returns_string_value(self):
        t = make_translations({"agent": {"key": "hello"}})
        assert t.resolve("agent.key") == "hello"

    def test_picks_from_list(self):
        options = ["a", "b", "c"]
        t = make_translations({"agent": {"key": options}})
        assert t.resolve("agent.key") in options

    def test_falls_back_to_fallback(self):
        t = make_translations(data={}, fallback={"agent": {"key": "fallback"}})
        assert t.resolve("agent.key") == "fallback"

    def test_returns_none_for_missing_key(self):
        t = make_translations({})
        assert t.resolve("agent.missing") is None

    def test_format_kwargs(self):
        t = make_translations({"msg": "Hello {name}"})
        assert t.resolve("msg", name="world") == "Hello world"

    def test_empty_list_returns_none(self):
        t = make_translations({"agent": {"key": []}})
        assert t.resolve("agent.key") is None

    def test_deep_nesting(self):
        t = make_translations({"a": {"b": {"c": "deep"}}})
        assert t.resolve("a.b.c") == "deep"


class TestLoad:
    def test_load_en(self, tmp_path):
        locales = tmp_path / "locales"
        locales.mkdir()
        (locales / "en.yaml").write_text(
            "research:\n  searching:\n    - Looking it up..."
        )
        t = ProgressTranslations.load("en", tmp_path)
        assert t.resolve("research.searching") == "Looking it up..."

    def test_load_pt_with_en_fallback(self, tmp_path):
        locales = tmp_path / "locales"
        locales.mkdir()
        (locales / "en.yaml").write_text("research:\n  searching:\n    - Searching...")
        (locales / "pt.yaml").write_text(
            "research:\n  searching:\n    - A pesquisar..."
        )
        t = ProgressTranslations.load("pt", tmp_path)
        assert t.resolve("research.searching") == "A pesquisar..."

    def test_missing_locale_file_falls_back_to_en(self, tmp_path):
        locales = tmp_path / "locales"
        locales.mkdir()
        (locales / "en.yaml").write_text("key: value")
        t = ProgressTranslations.load("fr", tmp_path)
        assert t.resolve("key") == "value"

    def test_missing_en_file_returns_none(self, tmp_path):
        (tmp_path / "locales").mkdir()
        t = ProgressTranslations.load("en", tmp_path)
        assert t.resolve("any.key") is None
