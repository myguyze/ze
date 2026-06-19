from __future__ import annotations

import dataclasses
from dataclasses import field as dc_field

from ze_components.schema import build_render_schema
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
