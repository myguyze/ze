from __future__ import annotations

from typing import TYPE_CHECKING

from ze_core.errors import AgentConfigError, UnknownAgentError

if TYPE_CHECKING:
    from ze_core.orchestration.base_agent import BaseAgent

_registry: dict[str, type[BaseAgent]] = {}
_instances: dict[str, BaseAgent] = {}


def agent(cls: type) -> type:
    """Register an agent class. Raises AgentConfigError on duplicate name."""
    name = getattr(cls, "name", None)
    if not name:
        raise AgentConfigError(f"{cls.__name__} must define a `name` class attribute")
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


def clear_registry() -> None:
    """Clear all registered agents and instances. Intended for use in tests only."""
    _registry.clear()
    _instances.clear()
