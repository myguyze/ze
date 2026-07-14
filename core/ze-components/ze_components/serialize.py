from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _drop_nones(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # Optional fields are non-nullable in the generated JSON schema — a null
    # value fails client-side validation and drops the whole tree.
    return {k: v for k, v in pairs if v is not None}


def serialize_primitive(node: object) -> dict[str, Any]:
    if not is_dataclass(node):
        raise TypeError(f"Expected a primitive dataclass, got {type(node)!r}")
    return asdict(node, dict_factory=_drop_nones)


def serialize_tree(roots: list[object]) -> list[dict[str, Any]]:
    return [serialize_primitive(node) for node in roots]
