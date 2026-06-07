#!/usr/bin/env python3
"""Generate JSON schema and Dart @freezed classes from Python component types.

Usage:
    uv run scripts/generate_components.py

Outputs:
    docs/component-schema.json
    packages/ze-flutter/lib/src/components/  (Dart files, if ze-flutter exists)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add packages to path so we can import ze_components
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "packages" / "ze-components"))
sys.path.insert(0, str(repo_root / "packages" / "ze-core"))

from ze_components.schema import export_json_schema
from ze_components.types import COMPONENT_TYPES, SUB_ITEM_TYPES

_DOCS_DIR = repo_root / "docs"
_FLUTTER_DIR = repo_root / "packages" / "ze-flutter" / "lib" / "src" / "components"

_DART_TYPE_MAP = {
    "string": "String",
    "integer": "int",
    "number": "double",
    "boolean": "bool",
    "array": "List",
    "object": "Map<String, dynamic>",
}


def _dart_type(schema: dict, nullable: bool = False) -> str:
    t = schema.get("type", "String")
    if t == "array":
        items = schema.get("items", {})
        inner = _dart_type(items)
        result = f"List<{inner}>"
    else:
        result = _DART_TYPE_MAP.get(t, "String")
    return f"{result}?" if nullable else result


def _emit_dart_freezed(cls: type, schema: dict, out_dir: Path) -> None:
    import dataclasses
    import typing

    class_name = cls.__name__
    snake = "".join(
        f"_{c.lower()}" if c.isupper() and i > 0 else c.lower()
        for i, c in enumerate(class_name.replace("Component", "").replace("Item", "").replace("Event", "").replace("Step", "").replace("Action", "").replace("Field", ""))
    )
    file_name = f"{snake}_component.dart" if "Component" in class_name else f"{snake}.dart"

    hints = typing.get_type_hints(cls)
    fields = [f for f in dataclasses.fields(cls) if f.init]
    required = schema.get("required", [])

    lines = [
        f"// GENERATED — do not edit. Run make generate-components to regenerate.",
        "import 'package:freezed_annotation/freezed_annotation.dart';",
        "",
        f"part '{file_name.replace('.dart', '.freezed.dart')}';",
        f"part '{file_name.replace('.dart', '.g.dart')}';",
        "",
        f"@freezed",
        f"class {class_name} with _${class_name} {{",
        f"  const factory {class_name}({{",
    ]

    for f in fields:
        nullable = f.name not in required
        prop_schema = schema.get("properties", {}).get(f.name, {"type": "string"})
        dart_t = _dart_type(prop_schema, nullable=nullable)
        prefix = "required " if not nullable else ""
        default = f' @Default(\'{f.default}\')" ' if f.default not in (dataclasses.MISSING, None) and not nullable else ""
        lines.append(f"    {prefix}{dart_t} {f.name},")

    lines += [
        "  }) = _" + class_name + ";",
        "",
        f"  factory {class_name}.fromJson(Map<String, dynamic> json) =>",
        f"      _${class_name}FromJson(json);",
        "}}",
    ]

    (out_dir / file_name).write_text("\n".join(lines))
    print(f"  Dart: {file_name}")


def _emit_dart_dispatcher(out_dir: Path) -> None:
    lines = [
        "// GENERATED — do not edit. Run make generate-components to regenerate.",
        "import 'package:ze_app/src/components/table_component.dart';",
    ]
    for cls in COMPONENT_TYPES:
        snake = cls.__name__.replace("Component", "").lower()
        lines.append(f"import 'package:ze_app/src/components/{snake}_component.dart';")

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

    # Dart @freezed classes (only if ze-flutter package exists)
    if _FLUTTER_DIR.parent.parent.parent.exists():
        _FLUTTER_DIR.mkdir(parents=True, exist_ok=True)
        from ze_components.schema import _dataclass_schema

        for cls in SUB_ITEM_TYPES + COMPONENT_TYPES:
            s = _dataclass_schema(cls)
            _emit_dart_freezed(cls, s, _FLUTTER_DIR)

        _emit_dart_dispatcher(_FLUTTER_DIR)
        print(f"Dart classes → {_FLUTTER_DIR}")
    else:
        print("ze-flutter not found — skipping Dart codegen")


if __name__ == "__main__":
    main()
