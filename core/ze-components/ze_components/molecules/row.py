from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Row:
    children: list
    gap: Literal["none", "sm", "md", "lg"] = "sm"
    align: Literal["start", "center", "end", "between"] = "start"
    type: Literal["row"] = field(default="row", init=False)


def row(children: list, *, gap: str = "sm") -> Row:
    return Row(children=children, gap=gap)  # type: ignore[arg-type]


def between(children: list, *, gap: str = "sm") -> Row:
    return Row(children=children, gap=gap, align="between")  # type: ignore[arg-type]


def center(children: list, *, gap: str = "sm") -> Row:
    return Row(children=children, gap=gap, align="center")  # type: ignore[arg-type]
