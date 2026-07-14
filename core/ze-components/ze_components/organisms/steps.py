from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StepItem:
    label: str
    status: str
    note: str | None = None


@dataclass
class Steps:
    steps: list[StepItem]
    title: str | None = None
    type: Literal["steps"] = field(default="steps", init=False)


def steps(items: list[StepItem], title: str | None = None) -> Steps:
    return Steps(steps=items, title=title)
