from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, get_type_hints

from ze_core.errors import AgentConfigError, UnknownToolError

_tools: dict[str, ToolSpec] = {}

_JSON_PRIMITIVE_TYPES = frozenset({str, int, float, bool, list, dict})

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


class ToolAccess(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass
class ToolSpec:
    name: str
    access: ToolAccess
    description: str
    func: Callable

    def llm_schema(self) -> dict:
        sig = inspect.signature(self.func)
        try:
            hints = get_type_hints(self.func)
        except Exception:
            hints = {}

        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            annotation = hints.get(param_name)
            if annotation not in _JSON_PRIMITIVE_TYPES:
                continue
            properties[param_name] = {"type": _PY_TO_JSON[annotation]}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


def tool(*, access: ToolAccess | str, description: str) -> Callable:
    """Decorator that registers an async function as a Ze Core tool."""
    access_val = ToolAccess(access) if isinstance(access, str) else access

    def _decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Tool {func.__name__!r} must be an async function")
        name = func.__name__
        if name in _tools:
            raise AgentConfigError(f"Duplicate tool name {name!r}")
        _tools[name] = ToolSpec(
            name=name, access=access_val, description=description, func=func
        )
        return func

    return _decorator


def get_tool(name: str) -> ToolSpec:
    try:
        return _tools[name]
    except KeyError:
        raise UnknownToolError(f"No tool registered with name {name!r}")


def registered_tools() -> dict[str, ToolSpec]:
    return dict(_tools)


def clear_tool_registry() -> None:
    """Clear all registered tools. Intended for use in tests only."""
    _tools.clear()
