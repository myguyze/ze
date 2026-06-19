from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Text:
    content: str
    style: Literal["heading", "subheading", "body", "label", "caption", "code"] = "body"
    color: Literal["default", "muted", "success", "warning", "error"] = "default"
    type: Literal["text"] = field(default="text", init=False)


def text(content: str, *, style: str = "body", color: str = "default") -> Text:
    return Text(content, style=style, color=color)  # type: ignore[arg-type]


def heading(content: str) -> Text:
    return Text(content, style="heading")


def subheading(content: str) -> Text:
    return Text(content, style="subheading")


def label(content: str) -> Text:
    return Text(content, style="label")


def caption(content: str) -> Text:
    return Text(content, style="caption")


def code(content: str) -> Text:
    return Text(content, style="code")


def muted(content: str) -> Text:
    return Text(content, color="muted")
