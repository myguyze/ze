from __future__ import annotations

from fastapi import FastAPI

from ze_logging import get_logger

log = get_logger(__name__)


def mount_plugin_routers(app: FastAPI, plugins: list) -> None:
    for plugin in plugins:
        plugin_name = type(plugin).__name__
        for router in plugin.rest_routes():
            app.include_router(router)
            log.info("plugin_router_mounted", plugin=plugin_name)
