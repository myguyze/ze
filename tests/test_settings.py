import pytest
from ze.settings import Settings, get_settings


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


def test_models_config_loads_yaml():
    s = make_settings()
    config = s.models_config
    assert "routing" in config
    assert "models" in config
    assert "threshold" in config["routing"]


def test_routing_config_shortcut():
    s = make_settings()
    rc = s.routing_config
    assert "threshold" in rc
    assert "gap_threshold" in rc
    assert "embedding_model" in rc


def test_agent_configs_loads_all_agents():
    s = make_settings()
    agents = s.agent_configs
    assert "research" in agents
    assert "companion" in agents
    assert "calendar" in agents
    assert "email" in agents
    assert "workflow" in agents


def test_agent_config_has_required_fields():
    s = make_settings()
    research = s.agent_configs["research"]
    assert "description" in research
    assert "model" in research
    assert "timeout_seconds" in research


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_confirm_timeout():
    s = make_settings()
    assert s.confirm_timeout_seconds == 900
