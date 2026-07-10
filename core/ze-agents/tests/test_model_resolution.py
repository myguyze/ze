import pytest

from ze_agents.errors import AgentConfigError
from ze_agents.model_resolution import (
    KNOWN_STEP_KEYS,
    resolve_model,
    validate_model_config,
)


class TestResolveModel:
    def test_override_wins_over_declared_and_default(self):
        config = {
            "models": {
                "default": "default/model",
                "overrides": {"companion": "override/model"},
            }
        }
        assert resolve_model("companion", "declared/model", config) == "override/model"

    def test_declared_wins_over_default_when_no_override(self):
        config = {"models": {"default": "default/model", "overrides": {}}}
        assert resolve_model("companion", "declared/model", config) == "declared/model"

    def test_default_used_when_no_override_or_declared(self):
        config = {"models": {"default": "default/model", "overrides": {}}}
        assert resolve_model("companion", None, config) == "default/model"

    def test_default_used_when_overrides_key_missing(self):
        config = {"models": {"default": "default/model"}}
        assert resolve_model("companion", None, config) == "default/model"

    def test_raises_when_no_default_and_no_declared(self):
        config = {"models": {"default": "", "overrides": {}}}
        with pytest.raises(AgentConfigError):
            resolve_model("companion", None, config)

    def test_raises_when_models_key_missing_entirely(self):
        config = {}
        with pytest.raises(AgentConfigError):
            resolve_model("companion", None, config)

    def test_removing_override_falls_back_to_declared(self):
        config = {
            "models": {
                "default": "default/model",
                "overrides": {"companion": "override/model"},
            }
        }
        assert resolve_model("companion", "declared/model", config) == "override/model"

        config["models"]["overrides"] = {}
        assert resolve_model("companion", "declared/model", config) == "declared/model"

    def test_removing_override_falls_back_to_default_when_no_declared(self):
        config = {
            "models": {
                "default": "default/model",
                "overrides": {"synthesis": "override/model"},
            }
        }
        assert resolve_model("synthesis", None, config) == "override/model"

        config["models"]["overrides"] = {}
        assert resolve_model("synthesis", None, config) == "default/model"


class TestValidateModelConfig:
    def test_passes_with_valid_config(self):
        config = {"models": {"default": "default/model", "overrides": {}}}
        validate_model_config(config, KNOWN_STEP_KEYS | {"companion"})

    def test_raises_when_default_missing(self):
        config = {"models": {"overrides": {}}}
        with pytest.raises(AgentConfigError):
            validate_model_config(config, KNOWN_STEP_KEYS)

    def test_raises_when_default_empty(self):
        config = {"models": {"default": "", "overrides": {}}}
        with pytest.raises(AgentConfigError):
            validate_model_config(config, KNOWN_STEP_KEYS)

    def test_raises_when_override_key_unknown(self):
        config = {
            "models": {
                "default": "default/model",
                "overrides": {"not_a_real_key": "some/model"},
            }
        }
        with pytest.raises(AgentConfigError):
            validate_model_config(config, KNOWN_STEP_KEYS | {"companion"})

    def test_raises_with_offending_key_named_in_message(self):
        config = {
            "models": {
                "default": "default/model",
                "overrides": {"compnaion": "some/model"},
            }
        }
        with pytest.raises(AgentConfigError, match="compnaion"):
            validate_model_config(config, KNOWN_STEP_KEYS | {"companion"})
