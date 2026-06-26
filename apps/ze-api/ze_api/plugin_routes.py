from __future__ import annotations

from fastapi import FastAPI

from ze_logging import get_logger

log = get_logger(__name__)


def mount_plugin_routers(app: FastAPI, plugins: list) -> None:
    for plugin in plugins:
        plugin_name = type(plugin).__name__
        routers = plugin.rest_routes()
        if not routers:
            continue
        log.info(
            "plugin_rest_routes_registered",
            plugin=plugin_name,
            count=len(routers),
            prefixes=[router.prefix or "/" for router in routers],
        )
        for router in routers:
            app.include_router(router)
