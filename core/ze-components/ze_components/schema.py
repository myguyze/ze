from __future__ import annotations

import dataclasses
import types
import typing

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}

_KNOWN_TYPES = frozenset([str, int, float, bool, list, dict, type(None)])


def _union_args(annotation: type) -> tuple[type, ...]:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return typing.get_args(annotation)
    return ()


def _unwrap_optional(annotation: type) -> tuple[type, bool]:
    args = _union_args(annotation)
    if args and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        return (non_none[0] if non_none else str), True
    return annotation, False


def _literal_schema(annotation: type) -> dict | None:
    if typing.get_origin(annotation) is typing.Literal:
        values = typing.get_args(annotation)
        if len(values) == 1:
            return {"const": values[0]}
        return {"enum": list(values)}
    return None


def _field_schema(annotation: type) -> dict:
    """Convert a single type annotation to a JSON schema fragment."""
    literal = _literal_schema(annotation)
    if literal is not None:
        return literal

    annotation, _ = _unwrap_optional(annotation)
    literal = _literal_schema(annotation)
    if literal is not None:
        return literal

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[annotation]}

    if origin is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _field_schema(item_type)}

    if dataclasses.is_dataclass(annotation):
        return _dataclass_schema(annotation)

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
    schema: dict = {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _discriminator_value(cls: type) -> str | None:
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        if f.init or f.name != "type":
            continue
        literal = _literal_schema(hints.get("type", str))
        if literal and "const" in literal:
            return literal["const"]
    return None


def _export_field_schema(
    annotation: type,
    *,
    field_name: str = "",
    primitive_ref: dict | None = None,
) -> dict:
    literal = _literal_schema(annotation)
    if literal is not None:
        return literal

    annotation, _ = _unwrap_optional(annotation)
    literal = _literal_schema(annotation)
    if literal is not None:
        return literal

    if field_name == "children" and primitive_ref is not None:
        return {"type": "array", "items": primitive_ref}

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[annotation]}

    if origin is list:
        item_type = args[0] if args else str
        if dataclasses.is_dataclass(item_type):
            return {
                "type": "array",
                "items": {"$ref": f"#/$defs/{item_type.__name__}"},
            }
        return {"type": "array", "items": _export_field_schema(item_type)}

    if dataclasses.is_dataclass(annotation):
        return {"$ref": f"#/$defs/{annotation.__name__}"}

    return {"type": "string"}


def _export_dataclass_schema(
    cls: type,
    *,
    primitive_ref: dict | None = None,
    include_discriminator: bool = False,
) -> dict:
    hints = typing.get_type_hints(cls)
    props: dict = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        if not f.init and not (include_discriminator and f.name == "type"):
            continue
        props[f.name] = _export_field_schema(
            hints[f.name],
            field_name=f.name,
            primitive_ref=primitive_ref,
        )
        if (
            f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        ) or (include_discriminator and f.name == "type"):
            required.append(f.name)
    schema: dict = {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }
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

    primitive_ref = {"$ref": "#/$defs/Primitive"}
    defs: dict = {}

    for cls in PRIMITIVE_SUB_TYPES:
        defs[cls.__name__] = _export_dataclass_schema(cls)

    discriminator_mapping: dict[str, str] = {}
    for cls in PRIMITIVE_TYPES:
        defs[cls.__name__] = _export_dataclass_schema(
            cls,
            primitive_ref=primitive_ref,
            include_discriminator=True,
        )
        discriminator = _discriminator_value(cls)
        if discriminator is not None:
            discriminator_mapping[discriminator] = f"#/$defs/{cls.__name__}"

    defs["Primitive"] = {
        "oneOf": [{"$ref": f"#/$defs/{cls.__name__}"} for cls in PRIMITIVE_TYPES],
        "discriminator": {
            "propertyName": "type",
            "mapping": discriminator_mapping,
        },
    }
    defs["PrimitiveTree"] = {
        "type": "array",
        "items": primitive_ref,
        "minItems": 1,
    }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Ze UI Primitives",
        "$defs": defs,
        "oneOf": [{"$ref": f"#/$defs/{cls.__name__}"} for cls in PRIMITIVE_TYPES],
        "discriminator": {
            "propertyName": "type",
            "mapping": discriminator_mapping,
        },
    }
