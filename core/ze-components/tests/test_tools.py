from __future__ import annotations

import pytest

import ze_components.tools  # noqa: F401 — ensures render tools are registered
from ze_components import context as ctx


async def test_render_table_appends_table_primitive():
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
    assert components[0]["title"] == "Results"
    assert "table" in result


async def test_render_metric_appends_col_primitive():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_metric(label="Revenue", value="$1,000")
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "col"
    # value is the first child (heading style)
    assert components[0]["children"][0]["content"] == "$1,000"
    assert "metric" in result


async def test_render_list_appends_col_primitive():
    token = ctx.begin_collection()
    await ze_components.tools.render_list(
        items=[{"text": "Task A", "status": "done"}, {"text": "Task B"}]
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "col"


async def test_render_list_rejects_non_dict_items():
    token = ctx.begin_collection()
    with pytest.raises(TypeError):
        await ze_components.tools.render_list(items=["not a dict"])
    ctx.collect_and_reset(token)


async def test_render_list_missing_required_field_raises():
    token = ctx.begin_collection()
    with pytest.raises(KeyError):
        await ze_components.tools.render_list(items=[{"label": "wrong key"}])
    ctx.collect_and_reset(token)


async def test_render_confirm_appends_col_with_buttons():
    token = ctx.begin_collection()
    await ze_components.tools.render_confirm(
        prompt="Delete this?",
        actions=[
            {"label": "Yes", "value": "yes", "style": "danger"},
            {"label": "No", "value": "no"},
        ],
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    c = components[0]
    assert c["type"] == "col"
    # first child is the prompt text
    assert c["children"][0]["content"] == "Delete this?"
    # second child is a row of buttons
    buttons_row = c["children"][1]
    assert buttons_row["type"] == "row"
    assert buttons_row["children"][0]["style"] == "danger"
    assert buttons_row["children"][1]["action"] == "no"


async def test_render_form_appends_form_primitive():
    token = ctx.begin_collection()
    await ze_components.tools.render_form(
        id="onboard-1",
        title="Tell me about yourself",
        fields=[{"id": "name", "label": "Your name", "field_type": "text"}],
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "form"
    assert components[0]["id"] == "onboard-1"
    assert components[0]["fields"][0]["id"] == "name"


async def test_render_connections_appends_connections_primitive():
    token = ctx.begin_collection()
    await ze_components.tools.render_connections(
        connections=[
            {
                "summary": "You often work late before deadlines",
                "narrative": "Several episodes mention late-night sessions",
                "relation": "pattern",
                "confidence": 0.8,
            }
        ]
    )
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "connections"
    assert components[0]["connections"][0]["relation"] == "pattern"


async def test_render_tool_confirmation_string_contains_tool_name():
    token = ctx.begin_collection()
    result = await ze_components.tools.render_table(
        headers=["A", "B"],
        rows=[["1", "2"], ["3", "4"]],
    )
    ctx.collect_and_reset(token)

    assert "table" in result


async def test_render_card_appends_col_primitive():
    token = ctx.begin_collection()
    await ze_components.tools.render_card(body="Something important", style="warning")
    components = ctx.collect_and_reset(token)

    assert len(components) == 1
    assert components[0]["type"] == "col"
    assert components[0]["variant"] == "section"
