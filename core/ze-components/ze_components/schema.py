from __future__ import annotations

import dataclasses
import typing

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}

_KNOWN_TYPES = frozenset([str, int, float, bool, list, dict, type(None)])


def _field_schema(annotation: type) -> dict:
    """Convert a single type annotation to a JSON schema fragment."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[annotation]}

    if origin is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _field_schema(item_type)}

    # handles X | None (Union) and Literal
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        return _field_schema(non_none[0]) if non_none else {"type": "string"}

    if dataclasses.is_dataclass(annotation):
        return _dataclass_schema(annotation)

    # Literal["a", "b", ...] — fall through to string (LLM sees description for valid values)
    return {"type": "string"}


def _dataclass_schema(cls: type) -> dict:
    """Build a JSON schema object from a dataclass."""
    hints = typing.get_type_hints(cls)
    props: dict = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        if not f.init:
            continue
        props[f.name] = _field_schema(hints[f.name])
        if (
            f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        ):
            required.append(f.name)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def build_render_schema(component_cls: type) -> dict:
    """Build the JSON schema parameters block for a render tool whose arguments
    match the component dataclass fields (excluding `type`)."""
    return _dataclass_schema(component_cls)


def export_json_schema() -> dict:
    """Generate a full JSON schema document with $defs for all primitive types."""
    from ze_components import PRIMITIVE_TYPES, PRIMITIVE_SUB_TYPES

    defs: dict = {}
    for cls in PRIMITIVE_SUB_TYPES + PRIMITIVE_TYPES:
        defs[cls.__name__] = _dataclass_schema(cls)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Ze UI Primitives",
        "$defs": defs,
        "oneOf": [{"$ref": f"#/$defs/{cls.__name__}"} for cls in PRIMITIVE_TYPES],
    }
