from ze_memory.admin import _aliases_from_row, _attrs_from_row


def test_aliases_from_row_parses_json_string():
    assert _aliases_from_row('["Marco"]') == ["Marco"]


def test_aliases_from_row_passes_through_list():
    assert _aliases_from_row(["Ana"]) == ["Ana"]


def test_attrs_from_row_parses_json_string():
    assert _attrs_from_row('{"role": "partner"}') == {"role": "partner"}


def test_attrs_from_row_passes_through_dict():
    assert _attrs_from_row({"level": "A2"}) == {"level": "A2"}
