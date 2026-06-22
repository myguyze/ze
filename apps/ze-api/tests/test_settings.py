import pytest
from ze_api.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_settings(**overrides) -> Settings:
    defaults = dict(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        ze_api_key="test-api-key",
    )
    return Settings(**{**defaults, **overrides})


def test_capabilities_path_points_to_config_dir(tmp_path):
    s = make_settings()
    assert s.capabilities_path.name == "config.yaml"
    assert s.capabilities_path.parent == s.config_dir


def test_config_loads_yaml():
    s = make_settings()
    config = s.config
    assert "models" in config
    assert "router" in config["models"]


def test_routing_config_defaults_empty_without_yaml_block():
    s = make_settings()
    assert s.routing_config == {}


def test_config_has_no_agents_block():
    s = make_settings()
    assert s.config.get("agents", {}) == {}


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_confirm_timeout():
    s = make_settings()
    assert s.confirm_timeout_seconds == 900


def test_auto_migrate_defaults_off():
    s = make_settings()
    assert s.auto_migrate is False


def test_auto_migrate_reads_env(monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE", "true")
    s = make_settings()
    assert s.auto_migrate is True
