from __future__ import annotations

from ze_components.schema import build_render_schema
from ze_components.types import (
    ListComponent,
    MetricComponent,
    TableComponent,
    TimelineComponent,
)


def test_build_render_schema_for_table():
    schema = build_render_schema(TableComponent)
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "headers" in props
    assert "rows" in props
    assert props["headers"]["type"] == "array"
    assert props["rows"]["type"] == "array"


def test_build_render_schema_required_fields():
    schema = build_render_schema(TableComponent)
    assert "headers" in schema["required"]
    assert "rows" in schema["required"]
    assert "title" not in schema.get("required", [])
    assert "caption" not in schema.get("required", [])


def test_build_render_schema_skips_type_discriminator():
    """The `type` field (init=False) must not appear in the schema."""
    for cls in [TableComponent, MetricComponent, ListComponent, TimelineComponent]:
        schema = build_render_schema(cls)
        assert "type" not in schema["properties"], f"{cls.__name__} has 'type' in schema"


def test_build_render_schema_nested_list_items():
    schema = build_render_schema(ListComponent)
    items_schema = schema["properties"]["items"]
    assert items_schema["type"] == "array"
    inner = items_schema["items"]
    assert inner["type"] == "object"
    assert "text" in inner["properties"]


def test_build_render_schema_metric_string_fields():
    schema = build_render_schema(MetricComponent)
    props = schema["properties"]
    assert props["label"]["type"] == "string"
    assert props["value"]["type"] == "string"
