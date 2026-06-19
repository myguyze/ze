from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Divider:
    type: Literal["divider"] = field(default="divider", init=False)


def divider() -> Divider:
    return Divider()
