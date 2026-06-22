from typing import Any, Protocol


class AutomationPlanner(Protocol):
    async def plan(self, prompt: str, **kwargs) -> list[Any]: ...


class AutomationStore(Protocol):
    async def get(self, id: str) -> Any | None: ...
    async def save(self, item: Any) -> None: ...
