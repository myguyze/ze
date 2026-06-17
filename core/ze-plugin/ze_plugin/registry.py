from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ze_plugin.plugin import ZePlugin

_registry: list[type[ZePlugin]] = []


def get_plugin_registry() -> list[type[ZePlugin]]:
    return list(_registry)
