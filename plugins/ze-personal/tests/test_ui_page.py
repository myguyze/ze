from __future__ import annotations

from uuid import uuid4

from ze_personal.contacts.types import Person
from ze_personal.ui.page import build_contacts_page


def _person(**overrides) -> Person:
    defaults = {
        "name": "Maria",
        "contact_info": {"email": "maria@example.com"},
        "notes": "Met at conference",
        "id": uuid4(),
    }
    defaults.update(overrides)
    return Person(**defaults)


def test_build_contacts_page_empty():
    tree = build_contacts_page([])
    assert len(tree) == 1
    assert tree[0]["type"] == "col"


def test_build_contacts_page_renders_contacts():
    tree = build_contacts_page([_person(), _person(name="João")])
    root = tree[0]
    assert root["type"] == "col"
    assert len(root["children"]) == 2
    assert root["children"][0]["type"] == "col"
    assert root["children"][0]["variant"] == "card"


def test_build_contacts_page_includes_email_and_notes():
    tree = build_contacts_page([_person()])
    card_children = tree[0]["children"][0]["children"]
    texts = [child.get("content") for child in card_children if child.get("type") == "text"]
    assert "Maria" in texts
    assert "maria@example.com" in texts
    assert "Met at conference" in texts
