import pytest
from ze_api.settings import Settings, get_settings
from ze_core.orchestration.registry import get_registered_agents


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
    assert "models" in config
    assert "router" in config["models"]


def test_routing_config_defaults_empty_without_yaml_block():
    s = make_settings()
    assert s.routing_config == {}


def test_agent_configs_empty_after_yaml_removal():
    s = make_settings()
    assert s.agent_configs == {}


def test_agents_registered_via_agent_decorator():
    import importlib
    from ze_api.bootstrap import _DEFAULT_AGENT_MODULE_PATHS
    for path in _DEFAULT_AGENT_MODULE_PATHS:
        importlib.import_module(path)
    agents = get_registered_agents()
    assert "research" in agents
    assert "companion" in agents
    assert "calendar" in agents
    assert "email" in agents
    assert "workflow" in agents
    assert "goals" in agents
    research = agents["research"]
    assert getattr(research, "description", "").strip()
    assert getattr(research, "model", "")


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_confirm_timeout():
    s = make_settings()
    assert s.confirm_timeout_seconds == 900
