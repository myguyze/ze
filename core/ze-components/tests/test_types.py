from __future__ import annotations

import dataclasses

from ze_components.types import (
    COMPONENT_TYPES,
    CardComponent,
    ConfirmAction,
    ConfirmComponent,
    ListComponent,
    ListItem,
    MetricComponent,
    TableComponent,
)


def test_asdict_produces_json_serializable_dict():
    tbl = TableComponent(
        headers=["Name", "Age"],
        rows=[["Alice", "30"], ["Bob", "25"]],
        title="People",
    )
    d = dataclasses.asdict(tbl)
    assert d["headers"] == ["Name", "Age"]
    assert d["rows"] == [["Alice", "30"], ["Bob", "25"]]
    assert d["title"] == "People"
    assert d["type"] == "table"


def test_type_discriminator_in_asdict():
    for cls in COMPONENT_TYPES:
        instance = _make_minimal(cls)
        d = dataclasses.asdict(instance)
        assert "type" in d, f"{cls.__name__} missing type in asdict"


def test_type_field_not_in_init():
    tbl = TableComponent(headers=[], rows=[])
    assert tbl.type == "table"

    metric = MetricComponent(label="Cost", value="$5")
    assert metric.type == "metric"


def test_list_component_with_list_items():
    lc = ListComponent(
        items=[ListItem(text="Task 1", status="done"), ListItem(text="Task 2")],
        title="Tasks",
    )
    d = dataclasses.asdict(lc)
    assert d["type"] == "list"
    assert len(d["items"]) == 2
    assert d["items"][0]["text"] == "Task 1"


def test_confirm_component_with_actions():
    cc = ConfirmComponent(
        prompt="Are you sure?",
        actions=[
            ConfirmAction(label="Yes", value="yes", style="primary"),
            ConfirmAction(label="No", value="no"),
        ],
    )
    d = dataclasses.asdict(cc)
    assert d["type"] == "confirm"
    assert d["actions"][0]["style"] == "primary"
    assert d["actions"][1]["style"] == "secondary"


def _make_minimal(cls: type) -> object:
    """Instantiate a component with minimal required fields."""
    import dataclasses as dc
    hints = {}
    kwargs = {}
    fields = [f for f in dc.fields(cls) if f.init]
    for f in fields:
        if f.default is dc.MISSING and f.default_factory is dc.MISSING:  # type: ignore[misc]
            ann = f.type
            if ann in ("str", str):
                kwargs[f.name] = "x"
            elif "list" in str(ann).lower():
                kwargs[f.name] = []
            else:
                kwargs[f.name] = "x"
    return cls(**kwargs)
