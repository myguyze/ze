from __future__ import annotations

import dataclasses
from dataclasses import field as dc_field

from ze_components.schema import build_render_schema, export_json_schema
from ze_components.organisms import Table


@dataclasses.dataclass
class _Inner:
    text: str
    subtext: str | None = None


@dataclasses.dataclass
class _Outer:
    items: list[_Inner]
    title: str | None = None


@dataclasses.dataclass
class _WithDiscriminator:
    label: str
    value: str
    type: str = dc_field(default="thing", init=False)


def test_build_render_schema_for_table():
    schema = build_render_schema(Table)
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "headers" in props
    assert "rows" in props
    assert props["headers"]["type"] == "array"
    assert props["rows"]["type"] == "array"


def test_build_render_schema_required_fields():
    schema = build_render_schema(Table)
    assert "headers" in schema["required"]
    assert "rows" in schema["required"]
    assert "title" not in schema.get("required", [])
    assert "caption" not in schema.get("required", [])


def test_build_render_schema_skips_init_false_fields():
    schema = build_render_schema(_WithDiscriminator)
    assert "type" not in schema["properties"]
    assert "label" in schema["properties"]
    assert "value" in schema["properties"]


def test_build_render_schema_nested_list_items():
    schema = build_render_schema(_Outer)
    items_schema = schema["properties"]["items"]
    assert items_schema["type"] == "array"
    inner = items_schema["items"]
    assert inner["type"] == "object"
    assert "text" in inner["properties"]


def test_build_render_schema_string_fields():
    schema = build_render_schema(_WithDiscriminator)
    props = schema["properties"]
    assert props["label"]["type"] == "string"
    assert props["value"]["type"] == "string"


def test_export_json_schema_includes_discriminators_and_recursive_children():
    schema = export_json_schema()
    col = schema["$defs"]["Col"]
    assert col["properties"]["type"] == {"const": "col"}
    assert col["properties"]["children"]["items"] == {"$ref": "#/$defs/Primitive"}
    assert "PrimitiveTree" in schema["$defs"]
    assert schema["$defs"]["PrimitiveTree"]["type"] == "array"


def test_export_json_schema_maps_progress_bar_type():
    schema = export_json_schema()
    assert schema["$defs"]["ProgressBar"]["properties"]["type"] == {"const": "progress"}


def test_export_json_schema_includes_steps():
    schema = export_json_schema()
    steps = schema["$defs"]["Steps"]
    assert steps["properties"]["type"] == {"const": "steps"}
    assert steps["properties"]["steps"]["items"] == {"$ref": "#/$defs/StepItem"}
    assert schema["$defs"]["StepItem"]["required"] == ["label", "status"]


def test_progress_steps_pattern_emits_steps_primitive():
    from ze_components.patterns import progress_steps
    from ze_components.serialize import serialize_primitive

    node = progress_steps(
        "Reach B1",
        [
            {"label": "A2 assessment", "status": "done"},
            {"label": "Conversation practice", "status": "active", "note": "2x weekly"},
        ],
    )
    data = serialize_primitive(node)
    assert data["type"] == "steps"
    assert data["title"] == "Reach B1"
    assert data["steps"][0] == {"label": "A2 assessment", "status": "done"}
    assert data["steps"][1]["note"] == "2x weekly"
