from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NotificationPriority = Literal[1, 2, 3, 4, 5]
# 1 = min  (silent background sync)
# 2 = low
# 3 = default
# 4 = high
# 5 = urgent (used for stuck goals, critical alerts)


@dataclass
class Notification:
    title: str
    body: str
    priority: NotificationPriority = 3
    tags: list[str] | None = None
    # Deep link payload. On tap, the web client can use this for in-app navigation.
    #   ze://navigate?<key>=<value>&...
    data: dict[str, str] | None = None
