from __future__ import annotations

from typing import TYPE_CHECKING

from ze_core.errors import AgentConfigError, UnknownAgentError

if TYPE_CHECKING:
    from ze_core.orchestration.base_agent import BaseAgent

_registry: dict[str, type[BaseAgent]] = {}
_instances: dict[str, BaseAgent] = {}


def agent(cls: type) -> type:
    """Register an agent class and validate its self-describing configuration.

    Accepts tools as either string names or callables; normalises callables to
    their ``__name__`` so downstream code always sees ``list[str]``.

    Raises AgentConfigError for: missing/empty name, missing/empty description,
    intent_map key not present in capabilities, duplicate name, or a tool entry
    that is neither a string nor a callable with ``__name__``.
    """
    name = getattr(cls, "name", None)
    if not name:
        raise AgentConfigError(f"{cls.__name__} must define a `name` class attribute")

    description = getattr(cls, "description", "").strip()
    if not description:
        raise AgentConfigError(f"Agent {name!r} must define a non-empty `description`")

    # Normalise tools: accept callables; extract __name__ so callers always
    # see list[str].  Validation against the tool registry is deferred to
    # Container._validate_registry (tools may not be registered yet at import time).
    raw_tools = list(getattr(cls, "tools", []))
    normalised: list[str] = []
    for t in raw_tools:
        if isinstance(t, str):
            normalised.append(t)
        elif callable(t):
            tool_name = getattr(t, "__name__", None)
            if not tool_name:
                raise AgentConfigError(
                    f"Agent {name!r}: tool {t!r} is callable but has no __name__"
                )
            normalised.append(tool_name)
        else:
            raise AgentConfigError(
                f"Agent {name!r}: tool entry {t!r} must be a string name or a callable"
            )
    cls.tools = normalised

    # When capabilities is declared, every intent_map key must be covered.
    # An empty capabilities dict means the agent hasn't declared gating rules;
    # the gate will default to AWAIT_CONFIRMATION for all intents.
    capabilities: dict = getattr(cls, "capabilities", {})
    if capabilities:
        for intent in getattr(cls, "intent_map", {}):
            if intent not in capabilities:
                raise AgentConfigError(
                    f"Agent {name!r} intent_map key {intent!r} not in capabilities"
                )

    if name in _registry:
        raise AgentConfigError(f"Duplicate agent name {name!r}")
    _registry[name] = cls
    return cls


def get_agent_class(name: str) -> type[BaseAgent]:
    """Return the registered class for `name`. Raises UnknownAgentError if missing."""
    try:
        return _registry[name]
    except KeyError:
        raise UnknownAgentError(f"No agent registered with name {name!r}")


def get_registered_agents() -> dict[str, type[BaseAgent]]:
    """Return all registered classes, including disabled ones."""
    return dict(_registry)


def get_enabled_agents() -> dict[str, type[BaseAgent]]:
    """Return only agents with enabled = True."""
    return {name: cls for name, cls in _registry.items() if getattr(cls, "enabled", True)}


def register_instance(name: str, instance: BaseAgent) -> None:
    """Register a live agent instance. Called by the container after DI wiring."""
    _instances[name] = instance


def get_agent(name: str) -> BaseAgent:
    """Return the live instance for `name`. Raises UnknownAgentError if not wired."""
    try:
        return _instances[name]
    except KeyError:
        raise UnknownAgentError(f"No agent instance registered for {name!r}")


def get_agent_instances() -> dict[str, BaseAgent]:
    """Return all registered live instances."""
    return dict(_instances)


def get_enabled_instances() -> dict[str, BaseAgent]:
    """Return all live instances (all registered instances are enabled by definition)."""
    return dict(_instances)


def clear_registry() -> None:
    """Clear all registered agents and instances. Intended for use in tests only."""
    _registry.clear()
    _instances.clear()
