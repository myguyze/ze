from __future__ import annotations

from ze_agents.errors import ZeCoreError


class MemoryError(ZeCoreError):
    pass


class RetrievalError(MemoryError):
    pass


class StoreError(MemoryError):
    pass


class PolicyError(MemoryError):
    pass


class UnknownModuleError(PolicyError):
    def __init__(self, module: str) -> None:
        super().__init__(f"no retrieval policy registered for module: {module!r}")
        self.module = module


class InvalidRetrievalRequestError(RetrievalError):
    pass
