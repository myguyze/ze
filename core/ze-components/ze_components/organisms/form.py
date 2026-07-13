from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal


@dataclass
class FormField:
    id: str
    label: str
    field_type: Literal[
        "text",
        "textarea",
        "number",
        "date",
        "select",
        "multiselect",
        "boolean",
        "chips",
    ] = "text"
    placeholder: str | None = None
    options: list[str] | None = None
    required: bool = True
    help_text: str | None = None
    default_value: str | None = None


@dataclass
class Form:
    id: str
    title: str
    fields: list[FormField]
    type: Literal["form"] = dc_field(default="form", init=False)


def form(id: str, title: str, fields: list[FormField]) -> Form:
    return Form(id=id, title=title, fields=fields)


def form_field(
    id: str,
    label: str,
    *,
    field_type: str = "text",
    placeholder: str | None = None,
    options: list[str] | None = None,
    required: bool = True,
    help_text: str | None = None,
    default_value: str | None = None,
) -> FormField:
    return FormField(  # type: ignore[arg-type]
        id=id,
        label=label,
        field_type=field_type,
        placeholder=placeholder,
        options=options,
        required=required,
        help_text=help_text,
        default_value=default_value,
    )
