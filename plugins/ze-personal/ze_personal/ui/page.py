from __future__ import annotations

from typing import Any

from ze_components.atoms import caption, muted, subheading, text
from ze_components.molecules import card, col
from ze_components.serialize import serialize_tree
from ze_personal.contacts.types import Person


def _contact_card(person: Person) -> object:
    body: list[object] = [subheading(person.name)]
    email = person.contact_info.get("email")
    if email:
        body.append(caption(email))
    if person.notes:
        body.append(muted(person.notes))
    return card(body)


def build_contacts_page(people: list[Person]) -> list[dict[str, Any]]:
    if not people:
        children: list[object] = [
            text("No contacts yet."),
            muted("Ze will learn about people from your conversations."),
        ]
    else:
        children = [_contact_card(person) for person in people]
    return serialize_tree([col(children)])
