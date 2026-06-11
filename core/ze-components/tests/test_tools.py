from __future__ import annotations

import dataclasses

import pytest

import ze_components.tools  # noqa: F401 — ensures render tools are registered
from ze_components import context as ctx
from ze_components.types import ConfirmComponent, ListComponent, TableComponent


async def test_render_table_appends_correct_dict():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_table(
        headers=["Name", "Score"],
        rows=[["Alice", "95"], ["Bob", "87"]],
        title="Results",
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "table"
    assert components[0]["headers"] == ["Name", "Score"]
    assert "Rendered table: Results (2 items)" in result


async def test_render_list_coerces_dicts_to_list_items():
    token = ctx.begin_collection()
    await ze_components.tools.render_list(
        items=[{"text": "Task A", "status": "done"}, {"text": "Task B"}]
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["items"][0]["text"] == "Task A"
    assert components[0]["items"][1]["subtext"] is None


async def test_render_list_raises_type_error_on_missing_field():
    token = ctx.begin_collection()
    with pytest.raises(TypeError):
        await ze_components.tools.render_list(
            items=[{"label": "wrong key — missing 'text'"}]
        )
    ctx.collect_and_reset(token)


async def test_render_confirm_produces_correct_component():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_confirm(
        prompt="Delete this?",
        actions=[{"label": "Yes", "value": "yes", "style": "danger"}, {"label": "No", "value": "no"}],
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    c = components[0]
    assert c["type"] == "confirm"
    assert c["prompt"] == "Delete this?"
    assert c["actions"][0]["style"] == "danger"
    assert c["actions"][1]["style"] == "secondary"


async def test_render_tool_confirmation_string_includes_type_and_count():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_table(
        headers=["A", "B"],
        rows=[["1", "2"], ["3", "4"], ["5", "6"]],
    )
    ctx.collect_and_reset(token)

    assert "table" in result
    assert "3 items" in result


async def test_render_metric_no_count_in_confirmation():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_metric(label="Revenue", value="$1,000")
    ctx.collect_and_reset(token)

    assert "metric" in result
    assert "Revenue" in result
