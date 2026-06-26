from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def serialize_primitive(node: object) -> dict[str, Any]:
    if not is_dataclass(node):
        raise TypeError(f"Expected a primitive dataclass, got {type(node)!r}")
    return asdict(node)


def serialize_tree(roots: list[object]) -> list[dict[str, Any]]:
    return [serialize_primitive(node) for node in roots]
