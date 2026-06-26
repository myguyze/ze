"""OpenAPI export with plugin REST routes included (for codegen)."""

from __future__ import annotations

import importlib
import json

from ze_plugin.bootstrap import load_plugin_classes


def collect_static_plugin_routers() -> list:
    """Import plugin route modules without instantiating plugins."""
    routers: list = []
    for _name, cls in load_plugin_classes():
        pkg = cls.__module__.rsplit(".", 1)[0]
        try:
            mod = importlib.import_module(f"{pkg}.api.routes")
        except ModuleNotFoundError:
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            routers.append(router)
    return routers


def export_openapi() -> dict:
    from ze_api.api.app import create_app

    app = create_app()
    for router in collect_static_plugin_routers():
        app.include_router(router)
    return app.openapi()


def main() -> None:
    print(json.dumps(export_openapi()))


if __name__ == "__main__":
    main()
