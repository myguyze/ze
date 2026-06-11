#!/usr/bin/env python3
"""Generate JSON schema and Dart @freezed classes from Python component types.

Usage:
    uv run scripts/generate_components.py

Outputs:
    docs/component-schema.json
    apps/ze-app/lib/src/components/  (Dart files, if ze-app exists)
"""
from __future__ import annotations

import dataclasses
import json
import sys
import types
import typing
from pathlib import Path

# Add core packages to path so we can import ze_components
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "core" / "ze-components"))
sys.path.insert(0, str(repo_root / "core" / "ze-core"))

from ze_components.schema import export_json_schema
from ze_components.types import COMPONENT_TYPES, SUB_ITEM_TYPES

_DOCS_DIR = repo_root / "docs"
_FLUTTER_DIR = repo_root / "apps" / "ze-app" / "lib" / "src" / "components"

_PY_ANNOTATION_TO_DART: dict[type, str] = {
    str: "String",
    int: "int",
    float: "double",
    bool: "bool",
}


def _to_camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _class_file_name(cls: type) -> str:
    class_name = cls.__name__
    snake = "".join(
        f"_{c.lower()}" if c.isupper() and i > 0 else c.lower()
        for i, c in enumerate(
            class_name.replace("Component", "")
            .replace("Item", "")
            .replace("Event", "")
            .replace("Step", "")
            .replace("Action", "")
            .replace("Field", "")
        )
    )
    return f"{snake}_component.dart" if "Component" in class_name else f"{snake}.dart"


def _unwrap_optional(annotation: type) -> tuple[type, bool]:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType) and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        return (non_none[0] if non_none else str), True
    return annotation, False


def _dart_type_from_annotation(annotation: type) -> str:
    annotation, _ = _unwrap_optional(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation in _PY_ANNOTATION_TO_DART:
        return _PY_ANNOTATION_TO_DART[annotation]

    if origin is list:
        item = args[0] if args else str
        return f"List<{_dart_type_from_annotation(item)}>"

    if dataclasses.is_dataclass(annotation):
        return annotation.__name__

    return "String"


def _referenced_dataclasses(annotation: type) -> set[type]:
    annotation, _ = _unwrap_optional(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if dataclasses.is_dataclass(annotation):
        return {annotation}

    if origin is list and args:
        return _referenced_dataclasses(args[0])

    return set()


def _default_suffix(field: dataclasses.Field) -> str:
    if field.default is dataclasses.MISSING or field.default is None:
        return ""
    if isinstance(field.default, str):
        return f" @Default('{field.default}')"
    return f" @Default({field.default!r})"


def _emit_dart_freezed(cls: type, schema: dict, out_dir: Path) -> None:
    class_name = cls.__name__
    file_name = _class_file_name(cls)

    hints = typing.get_type_hints(cls)
    fields = [f for f in dataclasses.fields(cls) if f.init]
    required = schema.get("required", [])

    nested = {
        ref
        for field in fields
        for ref in _referenced_dataclasses(hints[field.name])
        if ref is not cls
    }

    lines = [
        "// GENERATED — do not edit. Run make generate-components to regenerate.",
        "import 'package:freezed_annotation/freezed_annotation.dart';",
    ]
    for nested_cls in sorted(nested, key=lambda c: c.__name__):
        lines.append(
            f"import 'package:ze_app/src/components/{_class_file_name(nested_cls)}';"
        )
    lines += [
        "",
        f"part '{file_name.replace('.dart', '.freezed.dart')}';",
        f"part '{file_name.replace('.dart', '.g.dart')}';",
        "",
        "@freezed",
        f"class {class_name} with _${class_name} {{",
        f"  const factory {class_name}({{",
    ]

    for field in fields:
        dart_name = _to_camel_case(field.name)
        annotation = hints[field.name]
        _, optional_union = _unwrap_optional(annotation)
        has_default = (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING  # type: ignore[misc]
        )
        nullable = optional_union or (field.name not in required and not has_default)
        dart_t = _dart_type_from_annotation(annotation)
        if nullable and not dart_t.endswith("?"):
            dart_t = f"{dart_t}?"
        prefix = "required " if field.name in required else ""
        json_key = (
            f"@JsonKey(name: '{field.name}') "
            if dart_name != field.name
            else ""
        )
        default = _default_suffix(field) if has_default else ""
        lines.append(f"    {prefix}{json_key}{default}{dart_t} {dart_name},")

    lines += [
        "  }) = _" + class_name + ";",
        "",
        f"  factory {class_name}.fromJson(Map<String, dynamic> json) =>",
        f"      _${class_name}FromJson(json);",
        "}",
    ]

    (out_dir / file_name).write_text("\n".join(lines))
    print(f"  Dart: {file_name}")


def _emit_dart_dispatcher(out_dir: Path) -> None:
    lines = [
        "// GENERATED — do not edit. Run make generate-components to regenerate.",
    ]
    for cls in SUB_ITEM_TYPES + COMPONENT_TYPES:
        path = _class_file_name(cls)
        uri = f"package:ze_app/src/components/{path}"
        lines.append(f"import '{uri}';")
        lines.append(f"export '{uri}';")

    lines += [
        "",
        "// Dispatches JSON to the correct component class based on the 'type' field.",
        "dynamic componentFromJson(Map<String, dynamic> json) =>",
        "  switch (json['type'] as String) {",
    ]
    for cls in COMPONENT_TYPES:
        type_val = cls.__name__.replace("Component", "").lower()
        lines.append(f"    '{type_val}' => {cls.__name__}.fromJson(json),")
    lines += [
        "    _ => throw FormatException('Unknown component type: \\${json[\\'type\\']}')",
        "  };",
    ]

    (out_dir / "component_descriptor.dart").write_text("\n".join(lines))
    print("  Dart: component_descriptor.dart")


def main() -> None:
    # JSON schema
    _DOCS_DIR.mkdir(exist_ok=True)
    schema = export_json_schema()
    schema_path = _DOCS_DIR / "component-schema.json"
    schema_path.write_text(json.dumps(schema, indent=2))
    print(f"JSON schema → {schema_path}")

    # Dart @freezed classes (only if ze-app package exists)
    if _FLUTTER_DIR.parent.parent.parent.parent.exists():
        _FLUTTER_DIR.mkdir(parents=True, exist_ok=True)
        from ze_components.schema import _dataclass_schema

        for cls in SUB_ITEM_TYPES + COMPONENT_TYPES:
            s = _dataclass_schema(cls)
            _emit_dart_freezed(cls, s, _FLUTTER_DIR)

        _emit_dart_dispatcher(_FLUTTER_DIR)
        print(f"Dart classes → {_FLUTTER_DIR}")
    else:
        print("ze-app not found — skipping Dart codegen")


if __name__ == "__main__":
    main()
