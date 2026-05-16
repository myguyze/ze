from ze.errors import UnknownAgentError

_registry: dict[str, type] = {}
_instances: dict[str, object] = {}


def register(cls: type) -> type:
    """Class decorator that registers an agent class by its `name` attribute."""
    _registry[cls.name] = cls
    return cls


def register_instance(name: str, instance: object) -> None:
    """Register a live agent instance (called at app startup after DI wiring)."""
    _instances[name] = instance


def get_agent(name: str) -> object:
    if name not in _instances:
        raise UnknownAgentError(f"No registered instance for agent: {name!r}")
    return _instances[name]


def registered_names() -> list[str]:
    return list(_registry)
