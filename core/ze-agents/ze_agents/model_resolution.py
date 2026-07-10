"""Shared model resolution: override -> declared -> default.

Every general chat-completion call site resolves its model through
``resolve_model``. Capability-specific keys (``models.embedding``,
``models.whisper``, ``models.vision_caption``) are intentionally excluded
from this chain and keep their own explicit config lookups.
"""

from ze_agents.errors import AgentConfigError

KNOWN_STEP_KEYS: frozenset[str] = frozenset(
    {
        "router_fallback",
        "synthesis",
        "session_title",
        "workflow_verify",
        "insights",
        "reminders",
    }
)
"""Non-agent chat-completion call sites resolvable via the default/override chain."""


def resolve_model(key: str, declared: str | None, config: dict) -> str:
    """Resolve the effective model for ``key``.

    Resolution order: ``models.overrides[key]`` -> ``declared`` ->
    ``models.default``. Raises ``AgentConfigError`` if none of the three
    yields a model (i.e. ``declared`` is ``None`` and ``models.default`` is
    missing or empty).
    """
    models_cfg = config.get("models", {})
    overrides = models_cfg.get("overrides", {}) or {}

    override = overrides.get(key)
    if override:
        return override

    if declared:
        return declared

    default = models_cfg.get("default")
    if not default:
        raise AgentConfigError(
            f"no model resolvable for {key!r}: no override, no declared model, "
            "and models.default is missing or empty"
        )
    return default


def validate_model_config(config: dict, known_keys: frozenset[str]) -> None:
    """Fail fast at startup if ``models`` config is malformed.

    Raises ``AgentConfigError`` if ``models.default`` is missing/empty, or if
    any ``models.overrides`` key is not in ``known_keys``.
    """
    models_cfg = config.get("models", {})

    default = models_cfg.get("default")
    if not default:
        raise AgentConfigError("models.default is missing or empty in config.yaml")

    overrides = models_cfg.get("overrides", {}) or {}
    unknown_keys = sorted(set(overrides.keys()) - known_keys)
    if unknown_keys:
        raise AgentConfigError(
            f"unrecognized model key(s) in models.overrides: {unknown_keys}"
        )
